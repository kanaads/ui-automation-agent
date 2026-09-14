"""cua.replay.cli.execute: loads no artifact of its own and touches no
browser -- both `artifact` and `surface` are plain parameters, so this
is tested against the exact same `ScriptedSurface` fake
`cua.replay.engine`'s own unit tests use, and the same
`build_member_balance_artifact()` fixture. `main()` (untested at this
tier, same reasoning as cua.agent.cli's) is the only place that reads
`--artifact` off disk and wires a real Playwright browser.
"""
import json

import pytest

from cua.replay.cli import build_args, execute
from cua.surface.models import ActionResult, Observation
from tests.unit.replay.conftest import ScriptedSurface, build_member_balance_artifact, node

pytestmark = pytest.mark.unit


def _search_screen() -> Observation:
    return Observation(
        nodes=[node("txt1", "contentFrame", "textbox", "Member Number"), node("btn1", "contentFrame", "button", "Search")],
        url="http://x/content/search",
        title="Member Search",
    )


def _detail_screen() -> Observation:
    return Observation(
        nodes=[
            node("h1", "contentFrame", "heading", "Member Detail", depth=0),
            node("row1", "contentFrame", "row", None, depth=1),
            node("lbl1", "contentFrame", "cell", "Savings Balance", parent_ref="row1", depth=2),
            node("c1", "contentFrame", "cell", "$4,231.50", parent_ref="row1", depth=2),
            node("btn_confirm", "contentFrame", "button", "Confirm", depth=1),
        ],
        url="http://x/content/detail",
        title="Member Detail",
    )


def _member_lookup_surface() -> ScriptedSurface:
    """The full search -> detail flow build_member_balance_artifact()
    actually walks: a search screen with the real "Member Number"
    textbox and "Search" button, and a detail screen shaped so
    LABEL_PROXIMITY genuinely resolves "Savings Balance" -> the sibling
    value cell (a real row: a parent node plus two same-depth,
    same-parent_ref children), the same shape `cua.locator`'s own
    tests already prove that strategy against.
    """
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "btn1", advance=True)
    surface.script("contentFrame", "c1", result=ActionResult(ok=True, extracted_value="$4,231.50"), advance=False)
    return surface


def _args(tmp_path, **overrides):
    defaults = {"out": str(tmp_path / "out"), "param": ["member_id=10001"], "authorize": []}
    defaults.update(overrides)
    return build_args(**defaults)


def test_execute_on_success_saves_evidence_and_returns_zero(tmp_path):
    artifact = build_member_balance_artifact()
    surface = _member_lookup_surface()

    exit_code = execute(_args(tmp_path), artifact=artifact, surface=surface)

    assert exit_code == 0
    result = json.loads((tmp_path / "out" / "result.json").read_text())
    assert result["status"] == "success"
    assert result["outputs"]["balance_text"] == "$4,231.50"


def test_execute_on_a_business_outcome_still_returns_zero(tmp_path):
    not_found_screen = Observation(
        nodes=[node("g1", "contentFrame", "generic", "No records match your search.")],
        url="http://x/content/search",
        title="Member Search",
    )
    artifact = build_member_balance_artifact()
    surface = ScriptedSurface([not_found_screen])

    exit_code = execute(_args(tmp_path), artifact=artifact, surface=surface)

    assert exit_code == 0
    result = json.loads((tmp_path / "out" / "result.json").read_text())
    assert result["status"] == "business_outcome"
    assert result["outcome_code"] == "MEMBER_NOT_FOUND"


def test_execute_on_a_policy_block_returns_nonzero(tmp_path):
    """No --authorize was passed, and this artifact's real recorded
    flow (build_member_balance_artifact) has no risky step to block on
    -- so instead this proves the off-allowlist path via a domain the
    artifact's own policy_scope never declares, exercising the same
    guarded_replay() call execute() makes for real."""
    artifact = build_member_balance_artifact().model_copy(
        update={"policy_scope": build_member_balance_artifact().policy_scope.model_copy(update={"allowed_domains": ["nope.example"]})}
    )
    surface = ScriptedSurface([_detail_screen()])

    exit_code = execute(_args(tmp_path), artifact=artifact, surface=surface)

    assert exit_code == 1
    result = json.loads((tmp_path / "out" / "result.json").read_text())
    assert result["status"] == "policy_blocked"


def test_execute_passes_authorize_through_to_guarded_replay(tmp_path):
    """A RISKY_IRREVERSIBLE step with its id in --authorize must be let
    through; without it, the exact same run is blocked -- proving
    execute() genuinely wires authorized_step_ids, not just accepts
    the flag and drops it."""
    from cua.artifact.models import ActionType, RiskLevel, Step, Target
    from tests.unit.replay.conftest import role_tier

    risky_step = Step(
        step_id="click_confirm",
        action=ActionType.CLICK,
        target=Target(primary=role_tier("button", "Confirm")),
        risk=RiskLevel.RISKY_IRREVERSIBLE,
        risk_rationale="irreversible for this test",
    )
    base = build_member_balance_artifact(extra_steps=[risky_step])
    artifact = base.model_copy(
        update={"policy_scope": base.policy_scope.model_copy(update={"allowed_action_types": [*base.policy_scope.allowed_action_types, ActionType.CLICK]})}
    )
    surface = _member_lookup_surface()

    blocked = execute(_args(tmp_path, authorize=[]), artifact=artifact, surface=surface)
    assert blocked == 1
    blocked_result = json.loads((tmp_path / "out" / "result.json").read_text())
    assert blocked_result["status"] == "policy_blocked"

    surface2 = _member_lookup_surface()
    authorized = execute(_args(tmp_path, authorize=["click_confirm"]), artifact=artifact, surface=surface2)
    assert authorized == 0
