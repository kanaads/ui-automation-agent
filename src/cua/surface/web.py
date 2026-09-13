"""Playwright-backed Surface.

Perceives via `Locator.aria_snapshot(mode="ai")` on every frame -- the
main page plus every named iframe -- rather than the older
`Page.accessibility.snapshot()` API, which this project's pinned
Playwright version no longer exposes at all. `mode="ai"` is specifically
what hands back a stable `ref` per element that a same-process
`locator("aria-ref=...")` call can resolve back to a live element later;
the default/human-readable mode does not carry refs.

Refs are only valid against the DOM state they were captured from: after
any action that changes the page (most of them), a stale ref will simply
fail to resolve. That's intentional, not a bug to work around here --
the caller (locator resolution in `cua.locator`, or the agent loop) is
expected to `observe()` again before resolving/acting on the next step,
exactly as a human operator would look at the screen again after acting.
"""
from __future__ import annotations

from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from cua.artifact.models import ActionType
from cua.surface.aria_parser import parse_aria_snapshot
from cua.surface.base import Surface
from cua.surface.models import ActionResult, Observation, ObservedNode, SurfaceAction

MAIN_FRAME_LABEL = "main"

_REF_ACTIONS = frozenset(
    {
        ActionType.CLICK,
        ActionType.TYPE,
        ActionType.SELECT,
        ActionType.WAIT_FOR,
        ActionType.ASSERT_CHECKPOINT,
        ActionType.DISMISS,
        ActionType.EXTRACT,
    }
)


class WebSurface(Surface):
    def __init__(self, page: Page) -> None:
        self._page = page

    def _frame_label(self, frame: Frame) -> str:
        return frame.name or MAIN_FRAME_LABEL

    def _resolve_frame(self, label: str) -> Frame | None:
        if label == MAIN_FRAME_LABEL:
            return self._page.main_frame
        return self._page.frame(name=label)

    def observe(self) -> Observation:
        nodes: list[ObservedNode] = []
        for frame in self._page.frames:
            label = self._frame_label(frame)
            try:
                text = frame.locator(":root").aria_snapshot(mode="ai")
            except PlaywrightError:
                # A not-yet-loaded, detached, or cross-origin frame can
                # legitimately fail to snapshot; skip it rather than
                # failing the whole observation over one frame.
                continue
            nodes.extend(parse_aria_snapshot(text, frame=label))
        return Observation(nodes=nodes, url=self._page.url, title=self._page.title())

    def act(self, action: SurfaceAction) -> ActionResult:
        try:
            if action.action == ActionType.NAVIGATE:
                return self._navigate(action)
            if action.action in _REF_ACTIONS:
                return self._act_on_ref(action)
            # Unreachable while _REF_ACTIONS covers every ActionType
            # besides NAVIGATE; kept as a safety net if that enum grows.
            return ActionResult(ok=False, error=f"unsupported action '{action.action.value}'")  # pragma: no cover
        except PlaywrightTimeoutError as exc:
            return ActionResult(ok=False, error=f"timeout: {exc}")
        except PlaywrightError as exc:
            return ActionResult(ok=False, error=str(exc))

    def _navigate(self, action: SurfaceAction) -> ActionResult:
        target_frame = self._resolve_frame(action.frame) if action.frame else self._page.main_frame
        if target_frame is None:
            return ActionResult(ok=False, error=f"no such frame '{action.frame}'")
        url = urljoin(target_frame.url, action.value or "")
        target_frame.goto(url, timeout=action.timeout_ms)
        return ActionResult(ok=True)

    def _act_on_ref(self, action: SurfaceAction) -> ActionResult:
        if action.frame is None or action.ref is None:
            return ActionResult(ok=False, error=f"{action.action.value} requires a frame and a ref")
        frame = self._resolve_frame(action.frame)
        if frame is None:
            return ActionResult(ok=False, error=f"no such frame '{action.frame}'")

        locator = frame.locator(f"aria-ref={action.ref}")

        if action.action == ActionType.CLICK or action.action == ActionType.DISMISS:
            self._click_and_settle(frame, locator, action.timeout_ms)
            return ActionResult(ok=True)
        if action.action == ActionType.TYPE:
            locator.fill(action.value or "", timeout=action.timeout_ms)
            return ActionResult(ok=True)
        if action.action == ActionType.SELECT:
            locator.select_option(action.value or "", timeout=action.timeout_ms)
            return ActionResult(ok=True)
        if action.action in (ActionType.WAIT_FOR, ActionType.ASSERT_CHECKPOINT):
            locator.wait_for(state="visible", timeout=action.timeout_ms)
            return ActionResult(ok=True)
        if action.action == ActionType.EXTRACT:
            locator.wait_for(state="visible", timeout=action.timeout_ms)
            value = locator.text_content(timeout=action.timeout_ms) or ""
            return ActionResult(ok=True, extracted_value=value.strip())

        return ActionResult(ok=False, error=f"unsupported action '{action.action.value}'")  # pragma: no cover

    def _click_and_settle(self, frame: Frame, locator: Locator, timeout_ms: int) -> None:
        """A click that submits a form or follows a link only *starts* a
        navigation -- click() itself doesn't wait for it to finish.
        Confirmed live (repeatedly): without waiting for it, the very
        next `observe()` can race the redirect and see the stale
        pre-click document, reporting the step right after a navigating
        click as an unrecognized "target not found" roughly one time in
        five. A bare `frame.wait_for_load_state()` called *after*
        click() is not a fix either -- confirmed that returns
        immediately against the frame's pre-click load state too, since
        nothing has proven a navigation actually started yet by the
        time it's called.

        `expect_navigation()` is the correct tool precisely because it
        starts listening *before* the click happens, but it also raises
        `PlaywrightTimeoutError` for the ordinary, equally-valid case of
        a click that doesn't navigate at all -- indistinguishable by
        exception type from click() itself failing. `clicked` is what
        tells those two apart: it only flips to True once click() has
        actually returned, so a timeout with `clicked` still False is a
        real failure (re-raised, unchanged) and a timeout with it True
        is just "this click had nothing to wait for."
        """
        clicked = False
        try:
            with frame.expect_navigation(timeout=timeout_ms):
                locator.click(timeout=timeout_ms)
                clicked = True
        except PlaywrightTimeoutError:
            if not clicked:
                raise

    def screenshot(self) -> bytes:
        return self._page.screenshot()

    def current_url(self) -> str:
        return self._page.url
