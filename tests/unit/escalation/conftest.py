"""Fake stand-ins for the three Playwright objects cua.escalation.handoff
touches (`Page`, `BrowserContext`, `Browser`) -- just enough surface
(`evaluate`, `.contexts`, `.pages`) to unit-test the marker-search logic
with no real browser, no real CDP connection, and no Playwright import
at all. The real mechanics are proven live in
tests/integration/escalation.
"""
from __future__ import annotations

from collections.abc import Callable

from playwright.sync_api import Error as PlaywrightError


class FakePage:
    def __init__(self, marker: str | None = None, *, raises: bool = False) -> None:
        self._marker = marker
        self._raises = raises
        self.evaluate_calls: list[tuple[str, object]] = []

    def evaluate(self, script: str, arg: object = None) -> object:
        self.evaluate_calls.append((script, arg))
        if self._raises:
            # The exact exception type a real closed/mid-navigation
            # Playwright page raises -- reconnect_to_marked_page only
            # ever tolerates this one, never a blind `except Exception`.
            raise PlaywrightError("page is navigating or closed")
        if arg is not None:  # mark_page_for_handoff always passes the marker as arg
            self._marker = arg
            return None
        return self._marker  # reconnect_to_marked_page's read-only script passes none


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


class FakeBrowser:
    def __init__(self, contexts: list[FakeContext]) -> None:
        self.contexts = contexts


def fake_connector(browser: FakeBrowser) -> Callable[[str], FakeBrowser]:
    """A `connect_over_cdp`-shaped callable that always returns the same
    fake browser, regardless of endpoint -- what a test injects in place
    of a real Playwright driver's bound method."""

    def _connect(cdp_endpoint: str) -> FakeBrowser:
        return browser

    return _connect
