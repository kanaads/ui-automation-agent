"""cua.escalation.handoff, unit tier: the marker-write and marker-search
logic, against fake Playwright objects (tests/unit/escalation/conftest.py)
-- no real browser, no real CDP connection. `connect_over_cdp` is always
injected, the same dependency-injection pattern `cua.agent.llm`'s
provider clients already use for their own network/AWS boundary, so
this module never owns or starts a Playwright driver itself. The real
mechanics -- a second, independent connection genuinely finding and
proving it's the same live page -- are proven live in
tests/integration/escalation/test_handoff_live.py.
"""
import re

import pytest

from cua.escalation.handoff import (
    PageNotFoundError,
    mark_page_for_handoff,
    reconnect_to_marked_page,
)
from tests.unit.escalation.conftest import FakeBrowser, FakeContext, FakePage, fake_connector

pytestmark = pytest.mark.unit


def test_mark_page_for_handoff_writes_a_marker_and_returns_it():
    page = FakePage()

    marker = mark_page_for_handoff(page)

    assert re.fullmatch(r"[0-9a-f]{32}", marker)
    assert page.evaluate_calls[0][1] == marker
    assert "=" in page.evaluate_calls[0][0]


def test_mark_page_for_handoff_returns_a_fresh_marker_each_call():
    page = FakePage()

    assert mark_page_for_handoff(page) != mark_page_for_handoff(page)


def test_reconnect_finds_the_page_carrying_the_marker():
    target = FakePage(marker="the-real-one")
    decoy = FakePage(marker="something-else")
    browser = FakeBrowser([FakeContext([decoy, target])])

    found = reconnect_to_marked_page(
        "the-real-one", cdp_endpoint="http://x:1", connect_over_cdp=fake_connector(browser)
    )

    assert found is target


def test_reconnect_searches_every_context_not_just_the_first():
    target = FakePage(marker="the-real-one")
    browser = FakeBrowser([FakeContext([FakePage(marker="decoy")]), FakeContext([target])])

    found = reconnect_to_marked_page(
        "the-real-one", cdp_endpoint="http://x:1", connect_over_cdp=fake_connector(browser)
    )

    assert found is target


def test_reconnect_skips_a_page_that_throws_evaluating_the_marker():
    """A page mid-navigation or already closed can throw almost
    anything when evaluated against -- that's a reason to keep looking,
    never a reason to fail the whole search."""
    broken = FakePage(raises=True)
    target = FakePage(marker="the-real-one")
    browser = FakeBrowser([FakeContext([broken, target])])

    found = reconnect_to_marked_page(
        "the-real-one", cdp_endpoint="http://x:1", connect_over_cdp=fake_connector(browser)
    )

    assert found is target


def test_reconnect_raises_page_not_found_when_no_page_ever_matches(monkeypatch):
    browser = FakeBrowser([FakeContext([FakePage(marker="not-it")])])
    fake_time = iter([0.0, 100.0])  # first check is "now", second is already past any timeout
    monkeypatch.setattr("time.monotonic", lambda: next(fake_time))
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    with pytest.raises(PageNotFoundError, match="the-real-one"):
        reconnect_to_marked_page(
            "the-real-one", cdp_endpoint="http://x:1", connect_over_cdp=fake_connector(browser), timeout_s=1.0
        )


def test_reconnect_polls_until_the_marker_shows_up(monkeypatch):
    """The marker may not be there on the very first poll (a human's
    tool might reconnect a moment before the marker-writing script has
    actually run) -- confirm the search retries rather than giving up
    immediately."""
    page = FakePage(marker=None)
    browser = FakeBrowser([FakeContext([page])])
    monkeypatch.setattr("time.sleep", lambda _seconds: page.__setattr__("_marker", "the-real-one"))

    found = reconnect_to_marked_page(
        "the-real-one", cdp_endpoint="http://x:1", connect_over_cdp=fake_connector(browser), timeout_s=5.0
    )

    assert found is page
