"""Deterministic fault injection for the target app.

The assignment's whole premise is that a stable-UI legacy app still hits
real runtime errors: session timeouts, permission denials, unexpected
dialogs, slow loads, validation errors. Reproducing those "when it feels
like it" is useless for evidence -- so instead a test (or the evidence-run
script) arms a specific fault at a specific route ("hook point") for a
specific browser session, and the app consumes it exactly when that route
is next hit by that session.

Kept pure and HTTP-agnostic on purpose: fast to test in isolation, and the
app layer is a thin adapter around it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class HookPoint(str, Enum):
    """A point in the app's flow where a fault can be injected."""

    SEARCH = "search"
    DETAIL = "detail"
    SUBACCOUNT_NEW_SUBMIT = "subaccount_new_submit"
    SUBACCOUNT_CONFIRM = "subaccount_confirm"


class FaultCode(str, Enum):
    SESSION_TIMEOUT = "session_timeout"
    PERMISSION_DENIED = "permission_denied"
    SLOW_LOAD = "slow_load"
    SURPRISE_DIALOG = "surprise_dialog"
    VALIDATION_ERROR = "validation_error"


@dataclass
class ArmedFault:
    code: FaultCode
    occurrences: int = 1
    delay_ms: int = 0


@dataclass
class _Armed:
    code: FaultCode
    occurrences: int
    delay_ms: int


class FaultController:
    """Per-session, per-hook-point queue of armed faults.

    Faults for one session are invisible to every other session (two
    concurrent browser sessions -- e.g. an agent run and a human operator
    reviewing evidence -- never see each other's injected conditions), and
    faults for one hook point don't leak into another.
    """

    def __init__(self) -> None:
        self._armed: dict[tuple[str, HookPoint], list[_Armed]] = defaultdict(list)

    def arm(
        self,
        session_id: str,
        hook: HookPoint,
        code: FaultCode,
        occurrences: int = 1,
        delay_ms: int = 0,
    ) -> None:
        self._armed[(session_id, hook)].append(
            _Armed(code=code, occurrences=occurrences, delay_ms=delay_ms)
        )

    def consume(self, session_id: str, hook: HookPoint) -> ArmedFault | None:
        """Return the next armed fault for (session, hook), decrementing
        its remaining occurrences and dropping it once exhausted. Returns
        None if nothing is armed."""
        queue = self._armed.get((session_id, hook))
        if not queue:
            return None
        armed = queue[0]
        result = ArmedFault(code=armed.code, occurrences=armed.occurrences, delay_ms=armed.delay_ms)
        armed.occurrences -= 1
        if armed.occurrences <= 0:
            queue.pop(0)
        return result

    def clear(self, session_id: str, hook: HookPoint | None = None) -> None:
        if hook is not None:
            self._armed.pop((session_id, hook), None)
            return
        for key in [k for k in self._armed if k[0] == session_id]:
            self._armed.pop(key, None)

    def list_armed(self, session_id: str) -> dict[HookPoint, list[ArmedFault]]:
        result: dict[HookPoint, list[ArmedFault]] = {}
        for (sid, hook), queue in self._armed.items():
            if sid != session_id or not queue:
                continue
            result[hook] = [
                ArmedFault(code=a.code, occurrences=a.occurrences, delay_ms=a.delay_ms) for a in queue
            ]
        return result
