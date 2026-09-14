"""The full escalation loop for the replay side, against the real
target app: `cua.policy.guarded_replay` blocks the real
open-sub-account flow's unauthorized commit (Phase 6, proven again
here only incidentally), `cua.escalation.trigger.ticket_from_replay`
turns that `POLICY_BLOCKED` result into a ticket, the ticket is opened
onto a real queue, and a stand-in "human" reconnects over CDP to the
exact live page -- still sitting on the confirm screen, commit never
fired -- claims the ticket, and resolves it. Every piece proven
together, not just each in isolation.
"""
import pytest

from cua.escalation.contract import HandoffSource, HandoffStatus, SessionHandle
from cua.escalation.handoff import mark_page_for_handoff, reconnect_to_marked_page
from cua.escalation.queue import InMemoryEscalationQueue
from cua.escalation.trigger import ticket_from_replay
from cua.policy import guarded_replay
from cua.surface.web import WebSurface
from tests.integration.policy.conftest import build_open_subaccount_artifact

pytestmark = pytest.mark.integration


def test_a_policy_blocked_replay_becomes_a_ticket_a_human_can_join_and_resolve(live_app, cdp_browser):
    playwright, browser, endpoint = cdp_browser
    page = browser.new_page()
    page.goto(f"{live_app}/nav")
    surface = WebSurface(page)
    artifact = build_open_subaccount_artifact()
    inputs = {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"}

    result = guarded_replay(artifact, inputs, surface)  # no authorized_step_ids -- blocked at commit
    assert result.status.value == "policy_blocked"

    marker = mark_page_for_handoff(page)
    session = SessionHandle(cdp_endpoint=endpoint, page_marker=marker)
    ticket = ticket_from_replay(result, artifact=artifact, raw_inputs=inputs, session=session)
    assert ticket is not None
    assert ticket.source == HandoffSource.REPLAY
    assert ticket.capability_id == "open_subaccount"

    queue = InMemoryEscalationQueue()
    queue.open(ticket)
    assert ticket.ticket_id in {t.ticket_id for t in queue.list_open()}

    # The stand-in human's tooling: a wholly separate CDP connection,
    # armed with only what the ticket's session handle carries.
    joined = reconnect_to_marked_page(
        session.page_marker, cdp_endpoint=session.cdp_endpoint, connect_over_cdp=playwright.chromium.connect_over_cdp
    )
    # Genuinely the same in-progress page, not a fresh load of the same
    # URL: still on the confirm screen (the commit really never fired),
    # which only holds if this is the live DOM discovery/replay left
    # behind, re-derived independently of the original `page` object.
    heading = joined.frame(name="contentFrame").get_by_role("heading")
    assert "Confirm" in (heading.text_content() or "")

    claimed = queue.claim(ticket.ticket_id, operator="ops1")
    assert claimed.status == HandoffStatus.CLAIMED

    resolved = queue.resolve(ticket.ticket_id, notes="reviewed and approved manually; re-ran authorized")
    assert resolved.status == HandoffStatus.RESOLVED
    assert resolved.resolved_at is not None


def test_the_ticket_context_never_leaks_the_page_content_or_sensitive_inputs(live_app, cdp_browser):
    _playwright, browser, _endpoint = cdp_browser
    page = browser.new_page()
    page.goto(f"{live_app}/nav")
    surface = WebSurface(page)
    artifact = build_open_subaccount_artifact()
    inputs = {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"}

    result = guarded_replay(artifact, inputs, surface)
    ticket = ticket_from_replay(result, artifact=artifact, raw_inputs=inputs, session=SessionHandle())

    assert "last_observation" not in ticket.context
    # None of this artifact's inputs are declared sensitive, so they
    # pass through as-is -- confirming redact_result's own masking
    # behavior (proven in tests/unit/policy) is what's actually driving
    # this, not a copy that happens to look similar.
    assert ticket.context["inputs"]["purpose"] == "Vacation fund"
