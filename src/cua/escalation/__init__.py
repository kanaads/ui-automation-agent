"""Escalation & handoff: what happens when discovery or replay ends in
a status that needs a human.

- `cua.escalation.trigger.ticket_from_replay` / `ticket_from_discovery`
  turn an escalating `ReplayResult`/`DiscoveryResult` into a
  `HandoffTicket` (or `None`, if no escalation is needed).
- `cua.escalation.queue.InMemoryEscalationQueue` is the operator-facing
  state machine a raised ticket is opened onto (`OPEN -> CLAIMED ->
  {RESOLVED, ABANDONED}`).
- `cua.escalation.handoff.mark_page_for_handoff` /
  `reconnect_to_marked_page` are what make "the *same* live session"
  concrete: a separate process can attach to the exact running browser
  over CDP and find the exact tab discovery/replay was just driving.

`HandoffTicket`, `SessionHandle`, `HandoffStatus`, `HandoffSource` are
re-exported here from `cua.escalation.contract` for convenience.
"""
from cua.escalation.contract import HandoffSource, HandoffStatus, HandoffTicket, SessionHandle
from cua.escalation.handoff import (
    PageNotFoundError,
    mark_page_for_handoff,
    reconnect_to_marked_page,
)
from cua.escalation.queue import (
    EscalationQueue,
    HandoffStateError,
    InMemoryEscalationQueue,
    TicketNotFoundError,
)
from cua.escalation.trigger import ticket_from_discovery, ticket_from_replay

__all__ = [
    "EscalationQueue",
    "HandoffSource",
    "HandoffStateError",
    "HandoffStatus",
    "HandoffTicket",
    "InMemoryEscalationQueue",
    "PageNotFoundError",
    "SessionHandle",
    "TicketNotFoundError",
    "mark_page_for_handoff",
    "reconnect_to_marked_page",
    "ticket_from_discovery",
    "ticket_from_replay",
]
