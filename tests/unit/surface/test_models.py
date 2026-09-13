import pytest

from cua.artifact.models import ActionType
from cua.surface.models import ActionResult, Observation, ObservedNode, SurfaceAction

pytestmark = pytest.mark.unit


def _node(**kw) -> ObservedNode:
    defaults = {
        "ref": "e1",
        "frame": "contentFrame",
        "role": "button",
        "name": "Search",
        "attrs": {},
        "depth": 0,
        "parent_ref": None,
    }
    defaults.update(kw)
    return ObservedNode(**defaults)


class TestObservation:
    def test_find_by_ref_returns_the_matching_node(self):
        n1 = _node(ref="e1")
        n2 = _node(ref="e2", role="textbox", name=None)
        obs = Observation(nodes=[n1, n2], url="http://x/content/search", title="t")
        assert obs.find_by_ref("contentFrame", "e2") is n2

    def test_find_by_ref_is_scoped_to_frame(self):
        """Two different frames can legitimately produce the same raw ref
        (Playwright refs are only unique within a frame's snapshot), so
        lookups must be (frame, ref) pairs, never ref alone."""
        n1 = _node(ref="e1", frame="navFrame", role="generic", name=None)
        n2 = _node(ref="e1", frame="contentFrame", role="button", name="Search")
        obs = Observation(nodes=[n1, n2], url="u", title="t")
        assert obs.find_by_ref("navFrame", "e1") is n1
        assert obs.find_by_ref("contentFrame", "e1") is n2

    def test_find_by_ref_missing_returns_none(self):
        obs = Observation(nodes=[_node()], url="u", title="t")
        assert obs.find_by_ref("contentFrame", "nope") is None

    def test_by_role_name_matches_exact_role_and_name(self):
        obs = Observation(
            nodes=[_node(ref="e1", role="button", name="Search"), _node(ref="e2", role="button", name="Cancel")],
            url="u",
            title="t",
        )
        matches = obs.by_role_name("button", "Search")
        assert [n.ref for n in matches] == ["e1"]

    def test_by_role_name_can_be_scoped_to_a_frame(self):
        obs = Observation(
            nodes=[
                _node(ref="e1", frame="navFrame", role="button", name="Search"),
                _node(ref="e1", frame="contentFrame", role="button", name="Search"),
            ],
            url="u",
            title="t",
        )
        matches = obs.by_role_name("button", "Search", frame="contentFrame")
        assert len(matches) == 1
        assert matches[0].frame == "contentFrame"

    def test_by_text_near_matches_substring_in_any_node_name(self):
        obs = Observation(
            nodes=[_node(ref="e1", role="cell", name="Member Number:")],
            url="u",
            title="t",
        )
        assert len(obs.by_text_near("Member Number")) == 1
        assert len(obs.by_text_near("Nope")) == 0


class TestSurfaceAction:
    def test_minimal_navigate_action(self):
        a = SurfaceAction(action=ActionType.NAVIGATE, value="/content/search")
        assert a.ref is None
        assert a.frame is None
        assert a.timeout_ms == 5000

    def test_click_action_with_frame_and_ref(self):
        a = SurfaceAction(action=ActionType.CLICK, frame="contentFrame", ref="e13")
        assert a.frame == "contentFrame"
        assert a.ref == "e13"


class TestActionResult:
    def test_success_result_defaults(self):
        r = ActionResult(ok=True)
        assert r.error is None
        assert r.extracted_value is None

    def test_failure_result_carries_an_error(self):
        r = ActionResult(ok=False, error="timeout waiting for element")
        assert r.ok is False
        assert "timeout" in r.error
