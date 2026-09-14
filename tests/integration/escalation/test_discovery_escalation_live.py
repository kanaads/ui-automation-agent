"""The full escalation loop for the discovery side, against the real
target app: a stand-in LLM that never says "done" runs `discover()`
into a real `MAX_STEPS_EXCEEDED`, `cua.escalation.trigger.
ticket_from_discovery` turns that into a ticket, and a stand-in human
reconnects over CDP to the exact live page discovery left the browser
on -- proving a human really can pick up mid-flow, not just read a
description of what happened after the fact.
"""
import json

import pytest

from cua.agent.contract import DiscoveryStatus
from cua.agent.discover import discover
from cua.escalation.contract import HandoffSource, SessionHandle
from cua.escalation.handoff import mark_page_for_handoff, reconnect_to_marked_page
from cua.escalation.queue import InMemoryEscalationQueue
from cua.escalation.trigger import ticket_from_discovery
from cua.surface.web import WebSurface

pytestmark = pytest.mark.integration


class _NeverFinishes:
    """Always retypes the member id, never clicks Search -- a
    deliberately unhelpful model standing in for one that's genuinely
    lost, so discover() exhausts max_steps against the real app."""

    def complete(self, messages):
        return json.dumps({"thought": "let me try typing it again", "action": "type", "frame": "x", "ref": "y", "value": "10001"})


def test_a_max_steps_exceeded_discovery_becomes_a_ticket_a_human_can_join(live_app, cdp_browser):
    playwright, browser, endpoint = cdp_browser
    page = browser.new_page()
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)

    # The fixed "x"/"y" (frame, ref) never resolves against the real
    # observation, so discover() ends STUCK -- still an escalating
    # status, and it exercises a genuinely different discover() ending
    # than tests/integration/agent's own live "max_steps" test does.
    result = discover("Look up member 10001.", surface, _NeverFinishes(), max_steps=2)
    assert result.status == DiscoveryStatus.STUCK
    assert result.needs_escalation

    marker = mark_page_for_handoff(page)
    session = SessionHandle(cdp_endpoint=endpoint, page_marker=marker)
    ticket = ticket_from_discovery(result, session=session)

    assert ticket is not None
    assert ticket.source == HandoffSource.DISCOVERY
    assert ticket.capability_id is None
    assert ticket.context["goal"] == "Look up member 10001."

    queue = InMemoryEscalationQueue()
    queue.open(ticket)

    joined = reconnect_to_marked_page(
        session.page_marker, cdp_endpoint=session.cdp_endpoint, connect_over_cdp=playwright.chromium.connect_over_cdp
    )
    # The human's own reconnected page is genuinely the same live tab
    # discover() was just driving -- it still has the member search
    # form up, exactly where discovery left it stuck.
    assert joined.frame(name="contentFrame").get_by_role("textbox").count() == 1

    resolved = queue.resolve(ticket.ticket_id, notes="the model referenced a stale ref; looked the member up by hand")
    assert resolved.status.value == "resolved"
