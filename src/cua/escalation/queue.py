"""The operator-facing state machine around a `HandoffTicket`.

`EscalationQueue` is an abstract seam, deliberately: this project ships
one implementation, `InMemoryEscalationQueue`, in-process and
non-persistent, which is exactly right for a take-home demonstrating
the mechanism -- a real deployment would swap it for a durable, shared
store (a DB-backed queue, or a real ticketing system like PagerDuty or
Jira) without any caller of this interface needing to change (see
REPORT.md Section 7).

Legal transitions: `OPEN -> CLAIMED -> {RESOLVED, ABANDONED}`, with
`CLAIMED` skippable -- a human can resolve or abandon straight from
`OPEN` without a separate claim step, since not every deployment needs
one. Every other transition (claiming something already claimed,
resolving something already resolved, re-opening a ticket id that
already exists) raises rather than silently coercing or ignoring it --
the same "a state nobody declared is an error, not a guess" rule
`cua.replay.engine` and `cua.locator.resolve_target` already apply to
their own state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from cua.escalation.contract import HandoffStatus, HandoffTicket

_TERMINAL = frozenset({HandoffStatus.RESOLVED, HandoffStatus.ABANDONED})
_OPEN_ENOUGH_TO_CLOSE = frozenset({HandoffStatus.OPEN, HandoffStatus.CLAIMED})


class TicketNotFoundError(KeyError):
    """Raised for any operation on a `ticket_id` the queue has never
    seen `open()`ed -- distinct from `HandoffStateError`, which is for a
    ticket that exists but isn't in the right state for the requested
    transition."""


class HandoffStateError(ValueError):
    """Raised when a requested transition isn't legal from a ticket's
    current status (see module docstring for the legal graph)."""


class EscalationQueue(ABC):
    @abstractmethod
    def open(self, ticket: HandoffTicket) -> None: ...

    @abstractmethod
    def get(self, ticket_id: str) -> HandoffTicket | None: ...

    @abstractmethod
    def list_open(self) -> list[HandoffTicket]: ...

    @abstractmethod
    def claim(self, ticket_id: str, *, operator: str) -> HandoffTicket: ...

    @abstractmethod
    def resolve(self, ticket_id: str, *, notes: str = "") -> HandoffTicket: ...

    @abstractmethod
    def abandon(self, ticket_id: str, *, notes: str = "") -> HandoffTicket: ...


class InMemoryEscalationQueue(EscalationQueue):
    def __init__(self) -> None:
        self._tickets: dict[str, HandoffTicket] = {}

    def open(self, ticket: HandoffTicket) -> None:
        if ticket.ticket_id in self._tickets:
            raise HandoffStateError(f"a ticket with id '{ticket.ticket_id}' already exists")
        if ticket.status != HandoffStatus.OPEN:
            raise HandoffStateError(f"a newly opened ticket must be OPEN, not {ticket.status.value}")
        self._tickets[ticket.ticket_id] = ticket

    def get(self, ticket_id: str) -> HandoffTicket | None:
        return self._tickets.get(ticket_id)

    def list_open(self) -> list[HandoffTicket]:
        return [t for t in self._tickets.values() if t.status not in _TERMINAL]

    def claim(self, ticket_id: str, *, operator: str) -> HandoffTicket:
        ticket = self._require(ticket_id)
        if ticket.status != HandoffStatus.OPEN:
            raise HandoffStateError(f"ticket '{ticket_id}' must be OPEN to claim, not {ticket.status.value}")
        ticket.status = HandoffStatus.CLAIMED
        ticket.claimed_by = operator
        return ticket

    def resolve(self, ticket_id: str, *, notes: str = "") -> HandoffTicket:
        return self._close(ticket_id, HandoffStatus.RESOLVED, notes=notes)

    def abandon(self, ticket_id: str, *, notes: str = "") -> HandoffTicket:
        return self._close(ticket_id, HandoffStatus.ABANDONED, notes=notes)

    def _close(self, ticket_id: str, terminal_status: HandoffStatus, *, notes: str) -> HandoffTicket:
        ticket = self._require(ticket_id)
        if ticket.status not in _OPEN_ENOUGH_TO_CLOSE:
            raise HandoffStateError(
                f"ticket '{ticket_id}' is already {ticket.status.name}; cannot move it to {terminal_status.name}"
            )
        ticket.status = terminal_status
        ticket.resolution_notes = notes
        ticket.resolved_at = datetime.now(timezone.utc)
        return ticket

    def _require(self, ticket_id: str) -> HandoffTicket:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(f"no such ticket: '{ticket_id}'")
        return ticket
