"""cua.agent.discover.discover() against the REAL target app: a real
Chromium page, a real freshly-started app instance, and a real
WebSurface -- the first tier where the perceive-decide-act loop's
Surface-facing mechanics (locating a genuinely rendered textbox with no
accessible name, mapping a decision onto a real (frame, ref), acting,
re-observing a real DOM after a real page transition) are proven
against the real UI, not a ScriptedSurface (tests/unit/agent already
covers the loop's own branching logic exhaustively with one). Only the
LLM is faked here, per this tier's own rule (real browser + local fake
target app; LLM calls are fixture-driven) -- see tests/integration/policy
for the same split applied to cua.policy.guarded_replay.
"""
import pytest

from cua.agent.contract import DiscoveryStatus
from cua.agent.discover import discover
from cua.surface.web import WebSurface
from tests.integration.agent.conftest import LookUpMemberScript

pytestmark = pytest.mark.integration


def test_discover_completes_the_real_search_to_detail_flow(live_app, page):
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)
    llm = LookUpMemberScript(surface, member_id="10001")

    result = discover("Look up member 10001 and open their detail page.", surface, llm)

    assert result.status == DiscoveryStatus.GOAL_REACHED
    assert [step.decision.action for step in result.transcript] == ["type", "click"]
    assert result.final_observation is not None
    # the shell's top-level URL never changes (only contentFrame's src
    # does -- see shell.html), so success is checked the same way
    # tests/integration/surface/test_web_surface.py checks it: by the
    # real balance text the detail page renders, not the outer URL.
    assert result.final_observation.by_text_near("$4,231.50", frame="contentFrame")


def test_discover_records_real_frame_and_ref_values_that_actually_resolved(live_app, page):
    """Not hardcoded anywhere -- LookUpMemberScript looks its targets up
    fresh from the real Observation each turn, the same way a real model
    would from its rendered perception. This test only confirms the
    acted-on nodes were genuinely real (frame, ref) pairs the app itself
    assigned, not stand-ins."""
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)
    llm = LookUpMemberScript(surface, member_id="10001")

    result = discover("Look up member 10001 and open their detail page.", surface, llm)

    for step in result.transcript:
        assert step.decision.frame == "contentFrame"
        assert step.decision.ref
        assert step.observation.find_by_ref(step.decision.frame, step.decision.ref) is not None
        assert step.action_result.ok, step.action_result.error


def test_discover_reports_stuck_when_the_goal_is_unreachable_in_max_steps(live_app, page):
    """A deliberately unhelpful script (always re-types, never clicks
    Search) proves the real max_steps escape hatch fires against a real
    surface too, not just the ScriptedSurface unit tests."""
    page.goto(f"{live_app}/app")
    surface = WebSurface(page)

    class NeverFinishes:
        def complete(self, messages):
            import json

            obs = surface.observe()
            node = next(n for n in obs.nodes if n.role == "textbox" and n.frame == "contentFrame")
            return json.dumps({"thought": "typing again", "action": "type", "frame": node.frame, "ref": node.ref, "value": "10001"})

    result = discover("Look up member 10001.", surface, NeverFinishes(), max_steps=2)

    assert result.status == DiscoveryStatus.MAX_STEPS_EXCEEDED
    assert len(result.transcript) == 2
