"""The perceive-decide-act discovery loop: no artifact yet, just an LLM
choosing what to do next against a live `Surface`, one step at a time,
until it reports the goal reached (`"done"`), reports itself stuck
(`"stuck"`), a response fails to parse into a valid decision, an
attempted action genuinely fails, the model references a `(frame,
ref)` that isn't in the perception it was just given, or `max_steps` is
exhausted. Every one of those endings comes back as a `DiscoveryResult`
-- never an exception -- because an LLM saying something unusable is an
expected outcome of talking to one, not a bug in this loop.
`cua.agent.decide.AgentDecisionError` is caught right here, the one
place that's allowed to happen.

Deliberately mirrors `cua.replay.engine`'s own philosophy: never trust
a stale observation, never guess at a target that wasn't actually
proven to be there. The `(frame, ref)` existence check before acting is
this loop's equivalent of `cua.locator.resolve_target` refusing an
ambiguous match -- the LLM's claim that an element exists is checked
against the same `Observation` it was given, not taken on faith.

`cua.agent.recorder` is what turns a `GOAL_REACHED` result into a
reviewable `CapabilityArtifact`; this module only produces the raw
transcript.
"""
from __future__ import annotations

from cua.agent.contract import DiscoveryResult, DiscoveryStatus, DiscoveryStep
from cua.agent.decide import AgentDecision, AgentDecisionError, parse_agent_decision
from cua.agent.llm.base import LLMClient
from cua.agent.prompt import build_messages
from cua.artifact.models import ActionType
from cua.surface.base import Surface
from cua.surface.models import SurfaceAction

DEFAULT_MAX_STEPS = 15


def discover(goal: str, surface: Surface, llm: LLMClient, *, max_steps: int = DEFAULT_MAX_STEPS) -> DiscoveryResult:
    transcript: list[DiscoveryStep] = []
    observation = None

    for _ in range(max_steps):
        observation = surface.observe()

        try:
            decision = parse_agent_decision(llm.complete(build_messages(goal=goal, observation=observation, history=transcript)))
        except AgentDecisionError as exc:
            return DiscoveryResult(
                status=DiscoveryStatus.STUCK,
                goal=goal,
                transcript=transcript,
                reason=f"the model's response could not be parsed as a decision: {exc}",
                final_observation=observation,
            )

        if decision.action == "done":
            return DiscoveryResult(
                status=DiscoveryStatus.GOAL_REACHED,
                goal=goal,
                transcript=transcript,
                reason=decision.thought,
                final_observation=observation,
            )

        if decision.action == "stuck":
            return DiscoveryResult(
                status=DiscoveryStatus.STUCK, goal=goal, transcript=transcript, reason=decision.reason, final_observation=observation
            )

        if decision.action != "navigate":
            frame, ref = decision.frame, decision.ref
            # guaranteed non-None for every non-navigate action by AgentDecision's
            # own shape validator; asserted here only so mypy can narrow them.
            assert frame is not None and ref is not None
            if observation.find_by_ref(frame, ref) is None:
                return DiscoveryResult(
                    status=DiscoveryStatus.STUCK,
                    goal=goal,
                    transcript=transcript,
                    reason=f"the model referenced (frame={frame!r}, ref={ref!r}), which is not in the perception it was just given",
                    final_observation=observation,
                )

        action_result = surface.act(_to_surface_action(decision))
        transcript.append(DiscoveryStep(decision=decision, observation=observation, action_result=action_result))

        if not action_result.ok:
            return DiscoveryResult(
                status=DiscoveryStatus.STUCK,
                goal=goal,
                transcript=transcript,
                reason=f"action failed: {action_result.error}",
                final_observation=observation,
            )

    return DiscoveryResult(
        status=DiscoveryStatus.MAX_STEPS_EXCEEDED,
        goal=goal,
        transcript=transcript,
        reason=f"exceeded max_steps={max_steps} without the model reporting the goal reached",
        final_observation=observation,
    )


def _to_surface_action(decision: AgentDecision) -> SurfaceAction:
    return SurfaceAction(action=ActionType(decision.action), frame=decision.frame, ref=decision.ref, value=decision.value)
