"""WebSurface's CLICK/DISMISS handling must wait out a navigation the
click itself only *starts* -- confirmed live that skipping this makes
the very next observe() intermittently race the redirect (see the
docstring on `_click_and_settle`). Reliably forcing that exact race in
a real browser on demand isn't practical, so the three distinct
outcomes (navigates / doesn't / the click itself fails) are proven here
against lightweight fakes of Playwright's `expect_navigation()`
context-manager protocol instead.
"""
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from cua.artifact.models import ActionType
from cua.surface.models import SurfaceAction
from cua.surface.web import WebSurface

pytestmark = pytest.mark.unit


class _FakeExpectNavigation:
    """Mirrors the real context manager's contract, confirmed live in
    tests/integration/surface: if the body raises, that exception wins
    outright (no wait attempted); otherwise, __exit__ is where the
    navigation-timeout would surface."""

    def __init__(self, times_out: bool) -> None:
        self._times_out = times_out

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            return False  # let the body's own exception (click failing) propagate untouched
        if self._times_out:
            raise PlaywrightTimeoutError("Timeout 1000ms exceeded.\nwaiting for navigation until 'load'")
        return False


class _FakeLocator:
    def __init__(self, *, click_fails: bool = False) -> None:
        self._click_fails = click_fails

    def click(self, *, timeout=None):
        if self._click_fails:
            raise PlaywrightTimeoutError("Frame.click: Timeout 1000ms exceeded.\nwaiting for locator(...)")


class _FakeFrame:
    def __init__(self, *, navigates: bool) -> None:
        self.name = "contentFrame"
        self._navigates = navigates
        self.locator_obj = _FakeLocator()

    def locator(self, _selector):
        return self.locator_obj

    def expect_navigation(self, *, timeout=None):
        return _FakeExpectNavigation(times_out=not self._navigates)


class _FakePage:
    def __init__(self, frame: _FakeFrame) -> None:
        self._frame = frame

    def frame(self, *, name):
        return self._frame if name == self._frame.name else None


def _click_action(**overrides) -> SurfaceAction:
    defaults = {"action": ActionType.CLICK, "frame": "contentFrame", "ref": "e1", "timeout_ms": 1000}
    return SurfaceAction(**{**defaults, **overrides})


def test_click_that_navigates_settles_and_reports_ok():
    frame = _FakeFrame(navigates=True)
    surface = WebSurface(_FakePage(frame))  # type: ignore[arg-type]

    result = surface.act(_click_action())

    assert result.ok


def test_click_that_does_not_navigate_still_reports_ok():
    frame = _FakeFrame(navigates=False)
    surface = WebSurface(_FakePage(frame))  # type: ignore[arg-type]

    result = surface.act(_click_action())

    assert result.ok


def test_click_that_itself_fails_reports_the_real_failure_not_a_navigation_timeout():
    frame = _FakeFrame(navigates=True)  # irrelevant: click() never returns to reach the navigation wait
    frame.locator_obj = _FakeLocator(click_fails=True)
    surface = WebSurface(_FakePage(frame))  # type: ignore[arg-type]

    result = surface.act(_click_action())

    assert not result.ok
    assert "Frame.click" in (result.error or "")


def test_dismiss_action_goes_through_the_same_settle_path():
    frame = _FakeFrame(navigates=True)
    surface = WebSurface(_FakePage(frame))  # type: ignore[arg-type]

    result = surface.act(_click_action(action=ActionType.DISMISS))

    assert result.ok
