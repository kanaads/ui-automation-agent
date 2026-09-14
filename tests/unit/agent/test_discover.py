"""cua.agent.discover.discover(): the perceive-decide-act loop, driven
by a FakeLLMClient (a scripted queue of raw JSON replies) against a
ScriptedSurface (tests.unit.replay.conftest -- reused as-is, since a
Surface is a Surface regardless of what drives it) -- no browser, no
real LLM, and no JSON malformation left untested, since a real model's
replies must be treated as adversarial input, not trusted contracts.
"""
import json

import pytest

from cua.agent.contract import DiscoveryStatus
from cua.agent.discover import discover
from cua.surface.models import ActionResult, Observation
from tests.unit.agent.conftest import FakeLLMClient
from tests.unit.replay.conftest import ScriptedSurface, node

pytestmark = pytest.mark.unit


def _decision(action: str, **kwargs) -> str:
    return json.dumps({"thought": "t", "action": action, **kwargs})


def _search_screen() -> Observation:
    return Observation(
        nodes=[
            node("e1", "contentFrame", "document"),
            node("e10", "contentFrame", "textbox", None),
            node("e13", "contentFrame", "button", "Search"),
        ],
        url="http://x/content/search",
        title="Member Search",
    )


def _detail_screen() -> Observation:
    return Observation(
        nodes=[node("d2", "contentFrame", "heading", "Member Detail")],
        url="http://x/content/detail",
        title="Member Detail",
    )


def test_happy_path_reaches_goal_reached_and_records_only_the_acted_step():
    llm = FakeLLMClient(
        [
            _decision("click", frame="contentFrame", ref="e13"),
            _decision("done"),
        ]
    )
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "e13", advance=True)

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.GOAL_REACHED
    assert len(result.transcript) == 1
    assert result.transcript[0].decision.action == "click"
    assert result.transcript[0].decision.ref == "e13"
    # the "done" decision's own perception, never captured by transcript
    assert result.final_observation is not None
    assert result.final_observation.url == "http://x/content/detail"


def test_done_reason_is_the_models_thought():
    llm = FakeLLMClient([json.dumps({"thought": "member detail is now showing", "action": "done"})])
    surface = ScriptedSurface([_detail_screen()])

    result = discover("look up a member", surface, llm)

    assert result.reason == "member detail is now showing"


def test_stuck_decision_ends_the_run_with_the_models_reason():
    llm = FakeLLMClient([_decision("stuck", reason="no way to search from here")])
    surface = ScriptedSurface([_search_screen()])

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.STUCK
    assert result.reason == "no way to search from here"
    assert result.transcript == []


def test_an_unparseable_response_is_stuck_not_a_crash():
    llm = FakeLLMClient(["I think I should click the search button, but I'm not totally sure."])
    surface = ScriptedSurface([_search_screen()])

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.STUCK
    assert "could not be parsed" in result.reason
    assert result.transcript == []


def test_a_decision_referencing_a_nonexistent_ref_is_stuck_and_never_reaches_the_surface():
    llm = FakeLLMClient([_decision("click", frame="contentFrame", ref="does-not-exist")])
    surface = ScriptedSurface([_search_screen()])

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.STUCK
    assert "does-not-exist" in result.reason
    assert surface.actions == []


def test_a_decision_referencing_the_wrong_frame_for_a_real_ref_is_stuck():
    llm = FakeLLMClient([_decision("click", frame="navFrame", ref="e13")])
    surface = ScriptedSurface([_search_screen()])

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.STUCK
    assert surface.actions == []


def test_a_genuinely_failed_action_is_stuck_but_the_step_is_still_recorded():
    llm = FakeLLMClient([_decision("click", frame="contentFrame", ref="e13")])
    surface = ScriptedSurface([_search_screen()])
    surface.script("contentFrame", "e13", result=ActionResult(ok=False, error="timeout"))

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.STUCK
    assert "timeout" in result.reason
    assert len(result.transcript) == 1
    assert result.transcript[0].action_result.ok is False


def test_max_steps_exceeded_when_the_model_never_says_done_or_stuck():
    llm = FakeLLMClient([_decision("click", frame="contentFrame", ref="e13") for _ in range(3)])
    surface = ScriptedSurface([_search_screen()])  # never advances -- same screen every time

    result = discover("look up a member", surface, llm, max_steps=3)

    assert result.status == DiscoveryStatus.MAX_STEPS_EXCEEDED
    assert "max_steps=3" in result.reason
    assert len(result.transcript) == 3


def test_navigate_decision_maps_to_a_navigate_surface_action_with_no_frame_or_ref_check():
    llm = FakeLLMClient(
        [
            _decision("navigate", value="/app?start=/content/search"),
            _decision("done"),
        ]
    )
    surface = ScriptedSurface([_search_screen(), _search_screen()])

    result = discover("look up a member", surface, llm)

    assert result.status == DiscoveryStatus.GOAL_REACHED
    assert len(result.transcript) == 1
    nav_action = surface.actions[0]
    assert nav_action.frame is None
    assert nav_action.ref is None
    assert nav_action.value == "/app?start=/content/search"


def test_each_llm_call_receives_the_current_perception_and_growing_history():
    llm = FakeLLMClient(
        [
            _decision("click", frame="contentFrame", ref="e13"),
            _decision("done"),
        ]
    )
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "e13", advance=True)

    discover("look up a member", surface, llm)

    first_turn_user_message = llm.calls[0][-1].content
    assert "GOAL: look up a member" in first_turn_user_message
    assert "STEPS TAKEN SO FAR" not in first_turn_user_message

    second_turn_user_message = llm.calls[1][-1].content
    assert "STEPS TAKEN SO FAR" in second_turn_user_message
    assert "click" in second_turn_user_message
