"""The replay engine's result contract.

`ReplayStatus` is the error taxonomy the assignment asks for, made
concrete: `SUCCESS` and `BUSINESS_OUTCOME` are both legitimate, understood
endings for a capability invocation (the difference is only whether the
happy-path checkpoint was reached or a declared alternate ending was);
`RECOVERABLE` and `HARD_FAILURE` are the two declared-outcome categories
from `KnownOutcome.category` that mean the run stopped short;
`UNRECOGNIZED` is the engine's own signal for a state nobody declared --
the target couldn't be resolved (unambiguously or at all), or an action
genuinely failed -- and no `KnownOutcome` explains why; and
`POLICY_BLOCKED` means the run never even attempted a step because
something outside this module's own vocabulary (`cua.policy`, Phase 6)
declined it -- an off-allowlist domain, an unauthorized
`RiskLevel.RISKY_IRREVERSIBLE` step. Every status but the first two
means the same thing operationally (stop, capture context, hand off to
a human -- see `needs_escalation`); keeping them distinct is what lets a
human or the escalation layer (Phase 8) see *why* without having to
re-read the transcript.

`PolicyDecision`/`PolicyGuard` are the seam `cua.replay.engine.replay`
exposes for that gating without knowing anything about *why* a decision
came out the way it did: a guard is just `(Step, Observation) ->
PolicyDecision`, called fresh immediately before a step would otherwise
act, so it always sees the real, current page state -- not the
artifact's static declarations -- and can stop the engine before the
step's action ever reaches the Surface. `cua.replay` ships no guard of
its own (the default is `None`, meaning "run unrestricted," unchanged
from before this existed); `cua.policy` is what builds a real one.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cua.artifact.models import Step
from cua.surface.models import Observation


class ReplayStatus(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    RECOVERABLE = "recoverable"
    HARD_FAILURE = "hard_failure"
    UNRECOGNIZED = "unrecognized"
    POLICY_BLOCKED = "policy_blocked"


_ESCALATING = frozenset(
    {
        ReplayStatus.RECOVERABLE,
        ReplayStatus.HARD_FAILURE,
        ReplayStatus.UNRECOGNIZED,
        ReplayStatus.POLICY_BLOCKED,
    }
)


@dataclass
class ReplayResult:
    """What one `replay()` call hands back. Never raises for a runtime
    condition it can classify (see `cua.replay.inputs.ReplayInputError`
    for the one thing that *does* raise: a malformed invocation, which is
    a caller bug rather than something the UI did)."""

    status: ReplayStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    outcome_code: str | None = None
    failed_step_id: str | None = None
    reason: str = ""
    last_observation: Observation | None = None

    @property
    def needs_escalation(self) -> bool:
        return self.status in _ESCALATING


@dataclass
class PolicyDecision:
    """One guard's verdict on whether a single step may proceed. `allowed
    =False` stops `replay()` from ever calling `Surface.act()` for that
    step; `reason` flows straight into the resulting `ReplayResult`."""

    allowed: bool
    reason: str = ""


PolicyGuard = Callable[[Step, Observation], PolicyDecision]
