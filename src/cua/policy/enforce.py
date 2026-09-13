"""The ergonomic entry point: `guarded_replay` is what a caller (the
agent loop, Phase 7; escalation, Phase 8) reaches for by default --
`cua.replay.replay` itself stays reachable directly for anyone who
deliberately wants a run with no policy gating at all (e.g. a test
harness proving the engine's own mechanics in isolation, as
tests/unit/replay does).
"""
from __future__ import annotations

from collections.abc import Mapping

from cua.artifact.models import CapabilityArtifact
from cua.policy.guard import build_default_guard
from cua.replay import ReplayResult, replay
from cua.surface.base import Surface


def guarded_replay(
    artifact: CapabilityArtifact,
    raw_inputs: Mapping[str, object],
    surface: Surface,
    *,
    authorized_step_ids: frozenset[str] = frozenset(),
) -> ReplayResult:
    guard = build_default_guard(artifact, authorized_step_ids=authorized_step_ids)
    return replay(artifact, raw_inputs, surface, guard=guard)
