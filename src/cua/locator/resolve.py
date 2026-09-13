"""Resolves a Capability Artifact's tiered `Target` (Phase 1) against a
live `Observation` (Phase 3) into a concrete `(frame, ref)` -- or a
structured reason it couldn't, never a guess.

Per-strategy semantics, chosen to match what the target app actually
produces (verified live, not just imagined):

  ROLE_NAME        exact (role, name) match, searched across every frame.
                    Fails outright on a control with no accessible name --
                    that's expected, not a bug: it's what forces a real
                    fallback to LABEL_PROXIMITY.

  LABEL_PROXIMITY   find node(s) whose name contains `near_text` (the
                    label cell), then search that label's *row* --
                    concretely, the subtree rooted at the label's parent
                    -- for a descendant of role `control_type`. This
                    matches the real DOM shape our target app (and most
                    legacy table-based forms) produce: a row containing a
                    label cell and a sibling cell that *wraps* the actual
                    control, not a flat label-next-to-input structure.

  ANCHORED_REGION   a purely positional fallback, deliberately simple:
                    the `index`-th node whose role == `region`, in
                    document order, within `frame`. `region` names the
                    *target's own* role (e.g. "button"), not a container
                    to descend into -- "the 2nd button in this frame" is
                    directly actionable, whereas "the 2nd child of the
                    first rowgroup" usually lands on a row/cell wrapper,
                    not the leaf control, in a nested-table layout. Still
                    a real fallback distinct from tiers 1-2: no accessible
                    name and no nearby label text required, only a role
                    and a frame-scoped ordinal -- which is exactly what
                    survives a tenant's relabeling of a control's text.

  VISUAL_TEMPLATE   tier 4 is schema-validated (Phase 1) but intentionally
                    not executed here -- always contributes zero
                    candidates. See REPORT.md Section 7 (Cuts).

Ambiguity is never silently resolved by picking the first match --
`Target.ambiguity_policy` controls whether an ambiguous tier stops the
search immediately (`escalate_on_ambiguous`, the schema default) or is
merely noted while later tiers are still tried for a tier that IS unique
(`first_unique_match`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cua.artifact.models import LocatorStrategy, LocatorTier, Target
from cua.surface.models import Observation, ObservedNode


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass
class Resolution:
    status: ResolutionStatus
    frame: str | None = None
    ref: str | None = None
    tier_index: int | None = None
    strategy: LocatorStrategy | None = None
    candidates: list[ObservedNode] = field(default_factory=list)


def tier_matches(observation: Observation, tier: LocatorTier) -> list[ObservedNode]:
    """Public entry point for a caller that needs to check a single
    locator tier's presence directly, without Target's fallback-ladder
    or ambiguity-policy machinery -- e.g. `cua.replay`'s known-outcome
    detection, which only cares whether a declared marker (a heading, an
    error banner) is present anywhere, not about resolving it to exactly
    one actionable ref."""
    return _match_tier(observation, tier)


def resolve_target(observation: Observation, target: Target) -> Resolution:
    tiers = [target.primary, *target.fallbacks]
    first_ambiguous: tuple[int, LocatorTier, list[ObservedNode]] | None = None

    for tier_index, tier in enumerate(tiers):
        candidates = _match_tier(observation, tier)

        if len(candidates) == 1:
            node = candidates[0]
            return Resolution(
                status=ResolutionStatus.RESOLVED,
                frame=node.frame,
                ref=node.ref,
                tier_index=tier_index,
                strategy=tier.strategy,
                candidates=candidates,
            )

        if len(candidates) > 1:
            if target.ambiguity_policy == "escalate_on_ambiguous":
                return Resolution(
                    status=ResolutionStatus.AMBIGUOUS,
                    tier_index=tier_index,
                    strategy=tier.strategy,
                    candidates=candidates,
                )
            if first_ambiguous is None:
                first_ambiguous = (tier_index, tier, candidates)
            # first_unique_match: keep trying later tiers for a unique hit.

    if first_ambiguous is not None:
        tier_index, tier, candidates = first_ambiguous
        return Resolution(
            status=ResolutionStatus.AMBIGUOUS,
            tier_index=tier_index,
            strategy=tier.strategy,
            candidates=candidates,
        )
    return Resolution(status=ResolutionStatus.NOT_FOUND)


def _match_tier(observation: Observation, tier: LocatorTier) -> list[ObservedNode]:
    if tier.strategy == LocatorStrategy.ROLE_NAME:
        return observation.by_role_name(tier.params["role"], tier.params["name"])
    if tier.strategy == LocatorStrategy.LABEL_PROXIMITY:
        return _match_label_proximity(observation, tier.params["near_text"], tier.params["control_type"])
    if tier.strategy == LocatorStrategy.ANCHORED_REGION:
        return _match_anchored_region(
            observation, tier.params["frame"], tier.params["region"], tier.params["index"]
        )
    if tier.strategy == LocatorStrategy.VISUAL_TEMPLATE:
        return []  # deliberately not executed -- see module docstring
    return []  # pragma: no cover - exhaustive over LocatorStrategy


def _index_by_key(observation: Observation) -> dict[tuple[str, str], int]:
    return {(n.frame, n.ref): i for i, n in enumerate(observation.nodes) if n.ref is not None}


def _subtree(observation: Observation, root: ObservedNode) -> list[ObservedNode]:
    """The root plus every node that follows it in document order until
    depth returns to root's own depth (i.e. its full descendant tree),
    scoped to the same frame. Relies on Observation.nodes being in the
    pre-order traversal order the parser produced, which observe() and
    the aria parser both guarantee."""
    positions = _index_by_key(observation)
    start = positions.get((root.frame, root.ref)) if root.ref is not None else None
    if start is None:  # pragma: no cover - defensive only
        # Unreachable via the current caller: _match_label_proximity always
        # passes a `root` it already pulled out of this same `observation`,
        # so it is always present in `positions`. Kept as a guard rather
        # than an assert in case a future caller passes a detached node.
        return [root]
    result = [root]
    for n in observation.nodes[start + 1 :]:
        if n.frame != root.frame or n.depth <= root.depth:
            break
        result.append(n)
    return result


def _match_label_proximity(observation: Observation, near_text: str, control_type: str) -> list[ObservedNode]:
    anchors = observation.by_text_near(near_text)
    by_key = {(n.frame, n.ref): n for n in observation.nodes if n.ref is not None}

    matches: list[ObservedNode] = []
    for anchor in anchors:
        parent = by_key.get((anchor.frame, anchor.parent_ref)) if anchor.parent_ref is not None else None
        if parent is None:
            continue
        for candidate in _subtree(observation, parent):
            if candidate.role == control_type and candidate.ref != anchor.ref:
                matches.append(candidate)
    return matches


def _match_anchored_region(observation: Observation, frame: str, region: str, index: int) -> list[ObservedNode]:
    """`region` is the target's own role; `index` is its ordinal among
    nodes of that role within `frame`, in document order. Returns the
    node itself -- directly actionable -- never a container to descend
    into further."""
    matches = [n for n in observation.nodes if n.frame == frame and n.role == region]
    if 0 <= index < len(matches):
        return [matches[index]]
    return []
