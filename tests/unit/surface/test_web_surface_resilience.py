"""WebSurface.observe() must not fail the whole observation just because
one frame -- not yet loaded, detached, cross-origin -- can't produce a
snapshot right now. That's a real behavior worth unit-testing directly
against lightweight fakes rather than only exercising it incidentally
(or not at all) via the integration tier, since reliably forcing a real
browser frame into that state on demand isn't practical.
"""
import pytest
from playwright.sync_api import Error as PlaywrightError

from cua.surface.web import WebSurface

pytestmark = pytest.mark.unit


class _FakeLocator:
    def __init__(self, snapshot_text: str | None, error: Exception | None = None):
        self._snapshot_text = snapshot_text
        self._error = error

    def aria_snapshot(self, *, mode=None, **_kw):
        if self._error is not None:
            raise self._error
        return self._snapshot_text


class _FakeFrame:
    def __init__(self, name: str, snapshot_text: str | None = None, error: Exception | None = None):
        self.name = name
        self.url = f"http://x/{name or 'main'}"
        self._locator = _FakeLocator(snapshot_text, error)

    def locator(self, _selector):
        return self._locator


class _FakePage:
    def __init__(self, frames):
        self.frames = frames
        self.url = "http://x/app"

    def title(self):
        return "Meridian Core (mock)"


def test_observe_skips_a_frame_that_fails_to_snapshot_without_failing_the_rest():
    good = _FakeFrame("contentFrame", snapshot_text='- button "Search" [ref=e1]')
    broken = _FakeFrame("navFrame", error=PlaywrightError("frame is detached"))
    page = _FakePage([good, broken])

    surface = WebSurface(page)  # type: ignore[arg-type]
    obs = surface.observe()

    assert [n.frame for n in obs.nodes] == ["contentFrame"]
    assert obs.nodes[0].name == "Search"
