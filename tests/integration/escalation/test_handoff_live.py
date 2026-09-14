"""The core proof the assignment's escalation requirement actually asks
for: a human's own tooling can attach to the *same* live browser
session -- not a fresh one -- and find the exact tab, mid-flow, that
discovery or replay was just driving. `tests/unit/escalation/test_handoff.py`
already proves the marker-search logic against fakes; this proves the
real mechanics: a genuinely separate CDP connection, a genuinely real
Chromium process, no shortcuts.
"""
import pytest

from cua.escalation.handoff import (
    PageNotFoundError,
    mark_page_for_handoff,
    reconnect_to_marked_page,
)

pytestmark = pytest.mark.integration


def test_reconnect_over_cdp_finds_the_exact_same_live_page(live_app, cdp_browser):
    playwright, browser, endpoint = cdp_browser
    page = browser.new_page()
    page.goto(f"{live_app}/app")
    marker = mark_page_for_handoff(page)

    reconnected = reconnect_to_marked_page(
        marker, cdp_endpoint=endpoint, connect_over_cdp=playwright.chromium.connect_over_cdp
    )

    assert reconnected.url == page.url
    # The strongest available proof this is genuinely the SAME live
    # page rather than a lookalike: an action taken through the
    # reconnected handle is visible through the original one too --
    # they're two views onto one live DOM, not two separate pages.
    reconnected.evaluate("() => { window.__cua_proof_of_same_session = 'yes'; }")
    assert page.evaluate("() => window.__cua_proof_of_same_session") == "yes"


def test_reconnect_finds_the_right_page_among_several_open_tabs(live_app, cdp_browser):
    playwright, browser, endpoint = cdp_browser
    decoy1 = browser.new_page()
    decoy1.goto(f"{live_app}/app")
    target = browser.new_page()
    target.goto(f"{live_app}/content/detail?id=10001")
    decoy2 = browser.new_page()
    decoy2.goto(f"{live_app}/app")
    marker = mark_page_for_handoff(target)

    reconnected = reconnect_to_marked_page(
        marker, cdp_endpoint=endpoint, connect_over_cdp=playwright.chromium.connect_over_cdp
    )

    assert "detail" in reconnected.url


def test_reconnect_raises_page_not_found_for_a_marker_that_was_never_set(live_app, cdp_browser):
    playwright, browser, endpoint = cdp_browser
    page = browser.new_page()
    page.goto(f"{live_app}/app")

    with pytest.raises(PageNotFoundError):
        reconnect_to_marked_page(
            "no-such-marker",
            cdp_endpoint=endpoint,
            connect_over_cdp=playwright.chromium.connect_over_cdp,
            timeout_s=1.0,
            poll_interval_s=0.1,
        )
