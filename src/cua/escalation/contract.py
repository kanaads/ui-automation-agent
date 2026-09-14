"""The shape of one human escalation.

A `HandoffTicket` is raised whenever `cua.replay.replay()` or
`cua.agent.discover.discover()` ends in a status that "needs
escalation" (`ReplayResult.needs_escalation` /
`DiscoveryResult.needs_escalation` -- see `cua.escalation.trigger` for
the glue that actually builds one from either). It is deliberately
inert data with no behavior of its own: deciding which status
transitions are legal belongs to `cua.escalation.queue`'s state
machine, not to this dataclass, the same separation
`cua.replay.contract.ReplayResult` already draws between "what
happened" (this shape) and "what an engine does about it" (elsewhere).

`SessionHandle` is what makes the assignment's "hand off to a human on
the *same* live session" requirement concrete rather than aspirational:
it carries just enough for a *separate* process -- a human operator's
own tooling, never this one -- to attach to the exact running browser
(`cdp_endpoint`) and find the exact tab discovery or replay was just
driving (`page_marker`), via `cua.escalation.handoff`. Both fields are
optional: a caller that can't offer a live-rejoinable session (the
browser wasn't launched with a CDP port exposed, or a future
`DesktopSurface`-backed run with no such concept at all) can still
raise a ticket with a smaller guarantee -- "here's what happened and
why," just not "and you can jump into the exact same tab" (see
REPORT.md Section 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HandoffSource(str, Enum):
    DISCOVERY = "discovery"
    REPLAY = "replay"


class HandoffStatus(str, Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class SessionHandle:
    """Enough for a separate process to reconnect to the exact live
    browser session (not a fresh one) and find the exact tab. See the
    module docstring for why both fields are optional."""

    cdp_endpoint: str | None = None
    page_marker: str | None = None


@dataclass
class HandoffTicket:
    """One raised escalation. `context` is always a caller-redacted
    projection (see `cua.escalation.trigger`) -- this dataclass makes no
    redaction decisions of its own, the same way `ReplayResult` doesn't
    either; it only carries whatever it's handed."""

    ticket_id: str
    source: HandoffSource
    reason: str
    status_code: str
    capability_id: str | None
    context: dict[str, Any]
    session: SessionHandle
    status: HandoffStatus = HandoffStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    claimed_by: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
