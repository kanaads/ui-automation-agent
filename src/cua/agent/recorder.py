"""Turns a successful DiscoveryResult into a reviewable CapabilityArtifact
-- the "record" half of the assignment's discover -> record -> replay
pipeline. Two genuinely separate concerns, deliberately kept apart:

`infer_target` -- turning ONE acted (frame, ref) from ONE observation
into a resilient, tiered Target, the same ladder cua.locator already
matches against (ROLE_NAME -> LABEL_PROXIMITY -> ANCHORED_REGION): the
acted node's own accessible name if it has one and that name is a
stable UI label rather than the data the step just read (see
`treat_name_as_data` below); failing that, the nearest ancestor's
label-cell sibling (the exact "label cell, control cell, row siblings"
shape this project's target app uses -- see cua.locator's own
LABEL_PROXIMITY semantics, matched here in reverse: inferring the label
a proximity search would need, rather than searching for one given);
failing THAT, its ordinal position among same-role nodes in the frame,
as a last resort. Only a raw ref from ONE run was ever proven to work
here -- inventing a fallback tier that was never actually exercised
would be a guess dressed up as resilience, so `infer_target` returns a
single-tier Target (`primary` only, no `fallbacks`); adding fallbacks a
human reviewer trusts is exactly the kind of judgment call left to
them (see REPORT.md Section 7).

`treat_name_as_data` exists because of a real trap: an EXTRACT step's
target is often a table cell whose "name" (accessible text) *is* the
value being captured -- e.g. a balance cell literally named
"$4,231.50". That text is different on every replay by definition, so
using it as a ROLE_NAME locator would only ever match this one
member's balance again, never the next one's. `build_artifact_from_discovery`
passes `treat_name_as_data=True` for exactly the one action type where
this applies (EXTRACT), forcing target inference straight past the
name shortcut to the same label search a nameless control would get.

`build_artifact_from_discovery` -- the parts of a CapabilityArtifact
genuinely derivable from a transcript (each step's action/target,
`policy_scope.allowed_action_types` from what was actually used,
`policy_scope.allowed_domains` from every domain actually visited)
versus the parts that stay required, human-supplied arguments because
no transcript could answer them: `checkpoint` (what "success" means is
a decision, not an observation), `known_outcomes` (one happy-path run
proves nothing about what a session-timeout or access-denied screen
looks like), and every step's `risk`, which is always recorded as
`RiskLevel.SAFE` -- whether a step is actually irreversible is a
business judgment no DOM can answer, which is precisely why
`cua.policy` exists to let a human catch this before an artifact this
naive is ever replayed unattended.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cua.agent.contract import DiscoveryResult, DiscoveryStatus
from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    KnownOutcome,
    LocatorStrategy,
    LocatorTier,
    OutputSpec,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    Step,
    Target,
    TenantScope,
)
from cua.surface.models import Observation, ObservedNode

_VALUE_ACTIONS = frozenset({ActionType.TYPE, ActionType.SELECT})


def infer_target(observation: Observation, frame: str, ref: str, *, treat_name_as_data: bool = False) -> Target:
    node = observation.find_by_ref(frame, ref)
    if node is None:
        raise ValueError(f"no node (frame={frame!r}, ref={ref!r}) in this observation")

    if node.name and not treat_name_as_data:
        return Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": node.role, "name": node.name}))

    label = _infer_label(observation, frame, node)
    if label is not None:
        return Target(
            primary=LocatorTier(
                strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": label, "control_type": node.role}
            )
        )

    same_role = [n for n in observation.nodes if n.frame == frame and n.role == node.role]
    index = same_role.index(node)
    return Target(
        primary=LocatorTier(
            strategy=LocatorStrategy.ANCHORED_REGION, params={"frame": frame, "region": node.role, "index": index}
        )
    )


def _infer_label(observation: Observation, frame: str, node: ObservedNode) -> str | None:
    """Walks up from `node` itself: at each level, looks among the
    CURRENT node's own siblings (other nodes sharing its parent) for
    one with a name, then moves up to the parent and repeats. This
    covers both real shapes this project's target app produces -- a
    label cell and a value cell as direct row siblings (checked on the
    first pass), and a label cell as a sibling of a control's *wrapper*
    cell one level up (found on the second pass) -- without hardcoding
    which shape a given form uses.
    """
    current = node
    seen: set[str] = set()
    while current.parent_ref is not None and current.parent_ref not in seen:
        seen.add(current.parent_ref)
        for sibling in observation.nodes:
            if sibling.frame == frame and sibling.parent_ref == current.parent_ref and sibling.ref != current.ref and sibling.name:
                return sibling.name.rstrip(":").strip()
        parent = observation.find_by_ref(frame, current.parent_ref)
        if parent is None:
            return None
        current = parent
    return None


def build_artifact_from_discovery(
    result: DiscoveryResult,
    *,
    capability_id: str,
    version: str,
    description: str,
    tenant_scope: TenantScope,
    checkpoint: Checkpoint,
    known_outcomes: list[KnownOutcome] | None = None,
    input_schema: list[ParamSpec] | None = None,
    output_schema: list[OutputSpec] | None = None,
    parameterize: Mapping[str, str] | None = None,
    provenance: ProvenanceRecordedBy | None = None,
) -> CapabilityArtifact:
    if result.status != DiscoveryStatus.GOAL_REACHED:
        raise ValueError(
            f"cannot record an artifact from a discovery run that did not reach its goal (status={result.status.value})"
        )

    parameterize = parameterize or {}
    schema = list(input_schema or [])
    declared_names = {p.name for p in schema}
    for name in parameterize.values():
        if name not in declared_names:
            schema.append(ParamSpec(name=name, type=ParamType.STRING, required=True))
            declared_names.add(name)

    steps: list[Step] = []
    used_action_types: set[ActionType] = set()
    domains: set[str] = {urlsplit(observation.url).netloc for observation in _all_observations(result)}

    for i, discovery_step in enumerate(result.transcript, start=1):
        decision = discovery_step.decision
        action_type = ActionType(decision.action)
        used_action_types.add(action_type)
        step_id = f"step_{i}"

        if action_type == ActionType.NAVIGATE:
            input_param, literal_value = _parameterize_value(decision.value, parameterize)
            steps.append(Step(step_id=step_id, action=action_type, input_param=input_param, literal_value=literal_value))
            continue

        frame, ref = decision.frame, decision.ref
        assert frame is not None and ref is not None  # guaranteed for every non-navigate decision
        target = infer_target(discovery_step.observation, frame, ref, treat_name_as_data=action_type == ActionType.EXTRACT)

        if action_type in _VALUE_ACTIONS:
            input_param, literal_value = _parameterize_value(decision.value, parameterize)
            steps.append(
                Step(step_id=step_id, action=action_type, target=target, input_param=input_param, literal_value=literal_value)
            )
        elif action_type == ActionType.EXTRACT:
            steps.append(Step(step_id=step_id, action=action_type, target=target, output_field=decision.output_field))
        else:
            steps.append(Step(step_id=step_id, action=action_type, target=target))

    return CapabilityArtifact(
        capability_id=capability_id,
        version=version,
        description=description,
        tenant_scope=tenant_scope,
        input_schema=schema,
        output_schema=output_schema or [],
        steps=steps,
        checkpoint=checkpoint,
        known_outcomes=known_outcomes or [],
        policy_scope=PolicyScope(
            allowed_domains=sorted(domains), allowed_action_types=sorted(used_action_types, key=lambda a: a.value)
        ),
        provenance=provenance or ProvenanceRecordedBy(kind="llm_discovery", recorded_at=datetime.now(timezone.utc)),
    )


def _all_observations(result: DiscoveryResult) -> list[Observation]:
    observations = [ds.observation for ds in result.transcript]
    if result.final_observation is not None:
        observations.append(result.final_observation)
    return observations


def _parameterize_value(value: str | None, parameterize: Mapping[str, str]) -> tuple[str | None, str | None]:
    if value is not None and value in parameterize:
        return parameterize[value], None
    return None, value
