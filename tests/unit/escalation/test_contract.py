"""cua.escalation.contract: the shape of one human escalation. A
`HandoffTicket` is deliberately dumb data -- no behavior of its own --
so `cua.escalation.queue`'s state machine (test_queue.py) is the only
place that decides which status transitions are legal.
"""
from datetime import datetime, timezone

import pytest

from cua.escalation.contract import (
    HandoffSource,
    HandoffStatus,
    HandoffTicket,
    SessionHandle,
)

pytestmark = pytest.mark.unit


def test_a_ticket_defaults_to_open_with_no_claim_or_resolution():
    ticket = HandoffTicket(
        ticket_id="t1",
        source=HandoffSource.REPLAY,
        reason="policy blocked",
        status_code="policy_blocked",
        capability_id="open_subaccount",
        context={},
        session=SessionHandle(),
    )

    assert ticket.status == HandoffStatus.OPEN
    assert ticket.claimed_by is None
    assert ticket.resolution_notes is None
    assert ticket.resolved_at is None


def test_created_at_defaults_to_now_utc():
    before = datetime.now(timezone.utc)
    ticket = HandoffTicket(
        ticket_id="t1", source=HandoffSource.DISCOVERY, reason="stuck", status_code="stuck",
        capability_id=None, context={}, session=SessionHandle(),
    )
    after = datetime.now(timezone.utc)

    assert before <= ticket.created_at <= after
    assert ticket.created_at.tzinfo is not None


def test_two_tickets_get_independent_context_dicts():
    """A mutable default (context={}) shared across instances would be a
    classic dataclass footgun -- confirm each ticket gets its own dict."""
    t1 = HandoffTicket(
        ticket_id="t1", source=HandoffSource.DISCOVERY, reason="r", status_code="stuck",
        capability_id=None, context={}, session=SessionHandle(),
    )
    t2 = HandoffTicket(
        ticket_id="t2", source=HandoffSource.DISCOVERY, reason="r", status_code="stuck",
        capability_id=None, context={}, session=SessionHandle(),
    )

    t1.context["touched"] = True

    assert "touched" not in t2.context


def test_session_handle_defaults_to_no_live_rejoin_info():
    handle = SessionHandle()

    assert handle.cdp_endpoint is None
    assert handle.page_marker is None


def test_session_handle_carries_the_cdp_endpoint_and_marker():
    handle = SessionHandle(cdp_endpoint="http://127.0.0.1:9333", page_marker="abc123")

    assert handle.cdp_endpoint == "http://127.0.0.1:9333"
    assert handle.page_marker == "abc123"
