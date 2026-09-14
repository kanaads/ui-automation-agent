"""What one `cua.agent.discover.discover()` call hands back -- the raw
discovery transcript, one layer below a `CapabilityArtifact`.

Mirrors `cua.replay.contract`'s shape deliberately: a status enum, a
result dataclass with a `reason`, never an exception for an expected
outcome. `DiscoveryStatus.STUCK` here plays the same role
`ReplayStatus.RECOVERABLE`/`HARD_FAILURE`/`UNRECOGNIZED` do there --
the point a human should be looped in (Phase 8) -- but discovery only
has one flavor of "stopped short," since there's no artifact-declared
`KnownOutcome` taxonomy yet to classify against; that taxonomy is
exactly what a human reviewer adds *after* recording a successful run
(cua.agent.recorder), not something discovery can know in advance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cua.agent.decide import AgentDecision
from cua.surface.models import ActionResult, Observation


class DiscoveryStatus(str, Enum):
    GOAL_REACHED = "goal_reached"
    STUCK = "stuck"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"


_ESCALATING = frozenset({DiscoveryStatus.STUCK, DiscoveryStatus.MAX_STEPS_EXCEEDED})


@dataclass
class DiscoveryStep:
    """One action the agent actually took. A `done`/`stuck` decision,
    or a response that failed to parse, never becomes one of these --
    only genuinely acted steps end up here, since these (and only
    these) are what `cua.agent.recorder` turns into artifact `Step`s.
    """

    decision: AgentDecision
    observation: Observation
    action_result: ActionResult


@dataclass
class DiscoveryResult:
    status: DiscoveryStatus
    goal: str
    transcript: list[DiscoveryStep] = field(default_factory=list)
    reason: str = ""
    final_observation: Observation | None = None
    """The last thing the loop actually perceived before ending, for
    every ending -- including GOAL_REACHED, where it's the perception
    the model looked at when it said "done" (never captured by
    `transcript`, since a `done` decision has no corresponding acted
    step). Evidence/debugging use it as-is; `cua.agent.recorder` can
    use it to help a human reviewer choose the artifact's checkpoint.
    """

    @property
    def succeeded(self) -> bool:
        return self.status == DiscoveryStatus.GOAL_REACHED

    @property
    def needs_escalation(self) -> bool:
        return self.status in _ESCALATING
