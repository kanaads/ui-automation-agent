"""WebSurface against a real Chromium page and a real (locally running)
instance of the target app -- the first tier where "the agent must
actually interact with a real UI" (assignment 3.1) is genuinely true
rather than mocked.
"""
import pytest

from cua.artifact.models import ActionType
from cua.surface.models import SurfaceAction
from cua.surface.web import WebSurface

pytestmark = pytest.mark.integration


def test_observe_finds_the_hostile_unnamed_textbox_and_the_named_button(live_app, page):
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)
    obs = surface.observe()

    textboxes = [n for n in obs.nodes if n.role == "textbox" and n.frame == "contentFrame"]
    assert len(textboxes) == 1
    assert textboxes[0].name is None  # confirms the hostility end-to-end, not just in templates

    buttons = obs.by_role_name("button", "Search", frame="contentFrame")
    assert len(buttons) == 1


def test_observe_tags_nodes_from_both_named_frames(live_app, page):
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)
    obs = surface.observe()
    assert {"navFrame", "contentFrame"} <= {n.frame for n in obs.nodes}


def test_full_search_flow_via_semantic_actions_only(live_app, page):
    """No coordinates, no CSS selectors -- only (frame, ref) pairs handed
    back by observe(), which is the whole point of this layer."""
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)

    obs = surface.observe()
    textbox = next(n for n in obs.nodes if n.role == "textbox" and n.frame == "contentFrame")
    button = obs.by_role_name("button", "Search", frame="contentFrame")[0]

    typed = surface.act(SurfaceAction(action=ActionType.TYPE, frame=textbox.frame, ref=textbox.ref, value="10001"))
    assert typed.ok, typed.error

    clicked = surface.act(SurfaceAction(action=ActionType.CLICK, frame=button.frame, ref=button.ref))
    assert clicked.ok, clicked.error

    page.wait_for_timeout(200)
    obs2 = surface.observe()
    assert obs2.by_text_near("$4,231.50", frame="contentFrame")


def test_extract_reads_the_balance_cell_text(live_app, page):
    page.goto(f"{live_app}/content/detail?id=10001")
    surface = WebSurface(page)
    obs = surface.observe()
    balance_node = obs.by_text_near("$4,231.50")[0]

    result = surface.act(
        SurfaceAction(action=ActionType.EXTRACT, frame=balance_node.frame, ref=balance_node.ref)
    )
    assert result.ok
    assert result.extracted_value == "$4,231.50"


def test_click_on_a_nonexistent_ref_is_a_structured_failure_not_a_crash(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    result = surface.act(
        SurfaceAction(action=ActionType.CLICK, frame="main", ref="does-not-exist", timeout_ms=500)
    )
    assert result.ok is False
    assert result.error


def test_act_on_ref_without_a_frame_is_a_clear_error(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    result = surface.act(SurfaceAction(action=ActionType.CLICK, ref="e1"))
    assert result.ok is False
    assert "frame" in result.error


def test_navigate_action_changes_the_current_url(live_app, page):
    surface = WebSurface(page)
    result = surface.act(SurfaceAction(action=ActionType.NAVIGATE, value=f"{live_app}/content/search"))
    assert result.ok, result.error
    assert "content/search" in surface.current_url()


def test_navigate_to_an_unroutable_host_is_a_structured_failure(live_app, page):
    surface = WebSurface(page)
    result = surface.act(
        SurfaceAction(action=ActionType.NAVIGATE, value="http://127.0.0.1:1/nope", timeout_ms=800)
    )
    assert result.ok is False
    assert result.error


def test_select_action_changes_the_dropdown_value(live_app, page):
    page.goto(f"{live_app}/content/subaccount/new?id=10001")
    surface = WebSurface(page)
    obs = surface.observe()
    combobox = next(n for n in obs.nodes if n.role == "combobox")

    result = surface.act(
        SurfaceAction(action=ActionType.SELECT, frame=combobox.frame, ref=combobox.ref, value="CHECKING")
    )
    assert result.ok, result.error


def test_wait_for_and_assert_checkpoint_succeed_on_a_visible_element(live_app, page):
    page.goto(f"{live_app}/content/detail?id=10001")
    surface = WebSurface(page)
    heading = surface.observe().by_role_name("heading", "Member Detail")[0]

    waited = surface.act(SurfaceAction(action=ActionType.WAIT_FOR, frame=heading.frame, ref=heading.ref))
    assert waited.ok, waited.error

    checked = surface.act(
        SurfaceAction(action=ActionType.ASSERT_CHECKPOINT, frame=heading.frame, ref=heading.ref)
    )
    assert checked.ok, checked.error


def test_wait_for_a_missing_element_is_a_structured_failure(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    result = surface.act(
        SurfaceAction(action=ActionType.WAIT_FOR, frame="main", ref="nope", timeout_ms=500)
    )
    assert result.ok is False


def test_dismiss_action_clicks_the_surprise_dialog_ok_link(live_app, page):
    page.goto(f"{live_app}/content/search")  # establishes the session cookie
    surface = WebSurface(page)

    # page.request shares the page's cookie jar, so this arms the fault
    # against the SAME session the browser is using -- a separate HTTP
    # client with no cookies would arm a session the page never sees.
    page.request.post(f"{live_app}/debug/faults/arm", data={"hook": "search", "code": "surprise_dialog"})
    page.reload()
    ok_link = surface.observe().by_role_name("link", "OK")[0]

    result = surface.act(SurfaceAction(action=ActionType.DISMISS, frame=ok_link.frame, ref=ok_link.ref))
    assert result.ok, result.error


def test_act_with_unknown_frame_label_is_a_clear_error(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    result = surface.act(SurfaceAction(action=ActionType.CLICK, frame="not_a_real_frame", ref="e1"))
    assert result.ok is False
    assert "frame" in result.error


def test_navigate_with_unknown_frame_label_is_a_clear_error(live_app, page):
    surface = WebSurface(page)
    result = surface.act(
        SurfaceAction(action=ActionType.NAVIGATE, frame="not_a_real_frame", value="/content/search")
    )
    assert result.ok is False
    assert "frame" in result.error


def test_extract_on_a_missing_element_is_a_structured_failure(live_app, page):
    page.goto(f"{live_app}/content/detail?id=10001")
    surface = WebSurface(page)
    result = surface.act(
        SurfaceAction(action=ActionType.EXTRACT, frame="main", ref="nope", timeout_ms=500)
    )
    assert result.ok is False


def test_screenshot_returns_nonempty_bytes(live_app, page):
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    data = surface.screenshot()
    assert isinstance(data, bytes)
    assert len(data) > 100


def test_stale_ref_after_navigation_fails_cleanly(live_app, page):
    """Refs are only valid for the DOM state they were captured from --
    acting on one after the page has moved on must fail structurally,
    never silently act on the wrong element."""
    page.goto(f"{live_app}/content/search")
    surface = WebSurface(page)
    button = surface.observe().by_role_name("button", "Search")[0]

    page.goto(f"{live_app}/content/detail?id=10001")  # page moves on

    result = surface.act(
        SurfaceAction(action=ActionType.CLICK, frame=button.frame, ref=button.ref, timeout_ms=500)
    )
    assert result.ok is False
