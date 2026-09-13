"""The deterministic replay executor: no LLM in this loop.

`replay()` walks a CapabilityArtifact's steps against a `Surface`, in
order. For every targeted action it:

  1. Re-observes the surface fresh and checks every declared
     `KnownOutcome` *before* attempting to resolve the step's own
     target. A declared outcome always wins outright: if the page
     matches one, that's the answer, whatever the step itself wanted
     to do next -- this is what lets a fault (session timeout, a
     surprise dialog, "no such member") short-circuit the flow at
     exactly the point it actually occurred, rather than surfacing as a
     confusing failure one step later.
  2. Resolves `step.target` via `cua.locator.resolve_target`. Anything
     but a clean, unique RESOLVED becomes `UNRECOGNIZED` -- a state
     nobody declared -- never a guess.
  3. Acts, retrying up to `step.max_retries` times with a *fresh*
     observe()+resolve() each attempt: a stale ref from a failed
     attempt is meaningless to retry against, since whatever caused the
     failure may have changed the page.

`NAVIGATE` steps have no target to resolve; they retry the same literal
navigation directly. A NAVIGATE step's own fault, if any, surfaces at
the very next targeted step's pre-check (or the final one below) rather
than being checked twice.

Once every step has succeeded, the artifact's own `checkpoint` is
checked against one final fresh observation before `SUCCESS` is
returned: finishing the step list is not itself proof the goal was
reached (see REPORT.md Section 3).

Deliberately out of scope here (see REPORT.md Section 7): this engine
never attempts automatic recovery from a `recoverable` KnownOutcome
(e.g. dismissing a surprise dialog and resuming) -- it only detects and
classifies correctly. Acting on that classification (retry, dismiss,
hand off to a human) belongs to the agent loop (Phase 7) and the
escalation layer (Phase 8), which sit above this executor.

This engine carries no vocabulary for domains or risk levels -- it
can't gate a `RiskLevel.RISKY_IRREVERSIBLE` step or an off-allowlist
navigation on its own. What it does carry is one optional seam: an
injected `guard: PolicyGuard | None`, called fresh (a real `observe()`,
not the artifact's static declarations) immediately before *any* step
would otherwise act, NAVIGATE included. A guard that declines stops the
step's action from ever reaching the Surface and comes back as
`ReplayStatus.POLICY_BLOCKED`. With no guard (the default -- unchanged
from before this seam existed), every step runs exactly as before:
`cua.policy` (Phase 6) is what builds a real guard from an artifact's
`policy_scope` and a step's `risk`; this module still faithfully does
what the artifact says, nothing more cautious and nothing less, except
when a caller explicitly hands it a reason to pause first.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cua.artifact.models import ActionType, CapabilityArtifact, KnownOutcome, Step, Target
from cua.locator import Resolution, ResolutionStatus, resolve_target, tier_matches
from cua.replay.contract import PolicyGuard, ReplayResult, ReplayStatus
from cua.replay.inputs import validate_inputs
from cua.surface.base import Surface
from cua.surface.models import ActionResult, Observation, SurfaceAction

_CATEGORY_TO_STATUS: dict[str, ReplayStatus] = {
    "business_outcome": ReplayStatus.BUSINESS_OUTCOME,
    "recoverable": ReplayStatus.RECOVERABLE,
    "hard_failure": ReplayStatus.HARD_FAILURE,
}

_VALUE_SOURCE_ACTIONS = frozenset({ActionType.TYPE, ActionType.SELECT})


def replay(
    artifact: CapabilityArtifact,
    raw_inputs: Mapping[str, object],
    surface: Surface,
    *,
    guard: PolicyGuard | None = None,
) -> ReplayResult:
    inputs = validate_inputs(artifact, raw_inputs)
    outputs: dict[str, object] = {}
    last_step_id = artifact.steps[-1].step_id

    for step in artifact.steps:
        if step.action == ActionType.NAVIGATE:
            if guard is not None:
                blocked = _check_guard(guard, step, surface.observe(), outputs)
                if blocked is not None:
                    return blocked
            action = SurfaceAction(action=ActionType.NAVIGATE, value=_resolve_value(step, inputs), timeout_ms=step.timeout_ms)
            action_result = _act_with_retries(surface, action, step.max_retries)
            if not action_result.ok:
                return ReplayResult(
                    status=ReplayStatus.UNRECOGNIZED,
                    outputs=outputs,
                    failed_step_id=step.step_id,
                    reason=f"navigate failed: {action_result.error}",
                )
            continue

        if guard is not None:
            blocked = _check_guard(guard, step, surface.observe(), outputs)
            if blocked is not None:
                return blocked

        attempt = _run_targeted_step(surface, step, inputs, artifact.known_outcomes)

        if attempt.known_outcome is not None:
            return _outcome_result(attempt.known_outcome, step.step_id, outputs, attempt.observation)

        assert attempt.resolution is not None  # _run_targeted_step always sets this once known_outcome is None
        if attempt.resolution.status != ResolutionStatus.RESOLVED:
            return ReplayResult(
                status=ReplayStatus.UNRECOGNIZED,
                outputs=outputs,
                failed_step_id=step.step_id,
                reason=f"could not resolve target for step '{step.step_id}': {attempt.resolution.status.value}",
                last_observation=attempt.observation,
            )

        assert attempt.action_result is not None  # set as soon as resolution is RESOLVED
        if not attempt.action_result.ok:
            return ReplayResult(
                status=ReplayStatus.UNRECOGNIZED,
                outputs=outputs,
                failed_step_id=step.step_id,
                reason=f"action failed for step '{step.step_id}': {attempt.action_result.error}",
                last_observation=attempt.observation,
            )

        if step.action == ActionType.EXTRACT and step.output_field is not None:
            outputs[step.output_field] = attempt.action_result.extracted_value

    final_observation = surface.observe()
    outcome = _match_known_outcome(final_observation, artifact.known_outcomes)
    if outcome is not None:
        return _outcome_result(outcome, last_step_id, outputs, final_observation)

    checkpoint_resolution = resolve_target(final_observation, Target(primary=artifact.checkpoint.detection))
    if checkpoint_resolution.status == ResolutionStatus.RESOLVED:
        return ReplayResult(status=ReplayStatus.SUCCESS, outputs=outputs, last_observation=final_observation)

    return ReplayResult(
        status=ReplayStatus.UNRECOGNIZED,
        outputs=outputs,
        failed_step_id=last_step_id,
        reason="all steps completed but the artifact's checkpoint was not confirmed",
        last_observation=final_observation,
    )


def _check_guard(
    guard: PolicyGuard, step: Step, observation: Observation, outputs: dict[str, object]
) -> ReplayResult | None:
    """Returns a terminal `ReplayResult` if `guard` declines this step,
    else `None` (proceed). Kept as one shared call site for both the
    NAVIGATE branch and the targeted-step branch above, rather than
    duplicating the ReplayResult construction in each."""
    decision = guard(step, observation)
    if decision.allowed:
        return None
    return ReplayResult(
        status=ReplayStatus.POLICY_BLOCKED,
        outputs=outputs,
        failed_step_id=step.step_id,
        reason=decision.reason,
        last_observation=observation,
    )


@dataclass
class _Attempt:
    known_outcome: KnownOutcome | None = None
    resolution: Resolution | None = None
    action_result: ActionResult | None = None
    observation: Observation | None = None


def _run_targeted_step(
    surface: Surface, step: Step, inputs: dict[str, object], known_outcomes: list[KnownOutcome]
) -> _Attempt:
    assert step.target is not None  # guaranteed by Step's own schema validator for every non-navigate action
    attempts = step.max_retries + 1
    result = _Attempt()

    for attempt_num in range(attempts):
        last_attempt = attempt_num == attempts - 1
        observation = surface.observe()
        result.observation = observation

        outcome = _match_known_outcome(observation, known_outcomes)
        if outcome is not None:
            result.known_outcome = outcome
            return result

        resolution = resolve_target(observation, step.target)
        result.resolution = resolution
        if resolution.status != ResolutionStatus.RESOLVED:
            if last_attempt:
                return result
            continue

        value = _resolve_value(step, inputs) if step.action in _VALUE_SOURCE_ACTIONS else None
        action = SurfaceAction(
            action=step.action, frame=resolution.frame, ref=resolution.ref, value=value, timeout_ms=step.timeout_ms
        )
        action_result = surface.act(action)
        result.action_result = action_result
        if action_result.ok or last_attempt:
            return result

    raise AssertionError("unreachable: the loop above always returns on its last iteration")  # pragma: no cover


def _act_with_retries(surface: Surface, action: SurfaceAction, max_retries: int) -> ActionResult:
    result = surface.act(action)
    for _ in range(max_retries):
        if result.ok:
            break
        result = surface.act(action)
    return result


def _match_known_outcome(observation: Observation, known_outcomes: list[KnownOutcome]) -> KnownOutcome | None:
    for outcome in known_outcomes:
        if tier_matches(observation, outcome.detection):
            return outcome
    return None


def _outcome_result(
    outcome: KnownOutcome, step_id: str, outputs: dict[str, object], observation: Observation | None
) -> ReplayResult:
    return ReplayResult(
        status=_CATEGORY_TO_STATUS[outcome.category],
        outputs=outputs,
        outcome_code=outcome.code,
        failed_step_id=step_id,
        reason=outcome.description,
        last_observation=observation,
    )


def _resolve_value(step: Step, inputs: dict[str, object]) -> str:
    if step.literal_value is not None:
        return step.literal_value
    assert step.input_param is not None  # Step's schema validator requires exactly one of the two
    value = inputs[step.input_param]  # guaranteed present by validate_inputs' step-dependency check
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
