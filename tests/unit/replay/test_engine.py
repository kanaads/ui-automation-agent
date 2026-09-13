"""The replay engine, exercised against a fully scripted Surface --
no browser, no LLM. Screens mirror the exact node shapes proven live
against the real target app in Phase 3/4 (see tests/unit/locator's
fixtures and tests/integration/replay's live equivalents of these same
scenarios), so these aren't invented shapes that happen to make the
matcher happy.
"""
from datetime import datetime, timezone

import pytest

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    KnownOutcome,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    Step,
    Target,
    TenantScope,
)
from cua.replay import ReplayStatus, replay
from cua.replay.contract import PolicyDecision
from cua.surface.models import ActionResult, Observation
from tests.unit.replay.conftest import ScriptedSurface, node, role_tier

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Screens for the search -> detail flow (member_balance_artifact)
# ---------------------------------------------------------------------------

_SEARCH_NODES = [
    node("e1", "contentFrame", "document"),
    node("e2", "contentFrame", "generic", parent_ref="e1", depth=1),
    node("e3", "contentFrame", "heading", "Member Search", parent_ref="e2", depth=2),
    node("e5", "contentFrame", "table", parent_ref="e2", depth=2),
    node("e6", "contentFrame", "rowgroup", parent_ref="e5", depth=3),
    node("e7", "contentFrame", "row", parent_ref="e6", depth=4),
    node("e8", "contentFrame", "cell", "Member Number:", parent_ref="e7", depth=5),
    node("e9", "contentFrame", "cell", parent_ref="e7", depth=5),
    node("e10", "contentFrame", "textbox", parent_ref="e9", depth=6),
    node("e11", "contentFrame", "row", parent_ref="e6", depth=4),
    node("e12", "contentFrame", "cell", parent_ref="e11", depth=5),
    node("e13", "contentFrame", "button", "Search", parent_ref="e12", depth=6),
]

_DETAIL_NODES = [
    node("d1", "contentFrame", "document"),
    node("d2", "contentFrame", "heading", "Member Detail", parent_ref="d1", depth=1),
    node("d3", "contentFrame", "table", parent_ref="d1", depth=1),
    node("d4", "contentFrame", "rowgroup", parent_ref="d3", depth=2),
    node("d5", "contentFrame", "row", parent_ref="d4", depth=3),
    node("d6", "contentFrame", "cell", "Savings Balance:", parent_ref="d5", depth=4),
    node("d7", "contentFrame", "cell", "$4,231.50", parent_ref="d5", depth=4),
]


def search_screen(marker: tuple[str, str] | None = None) -> Observation:
    nodes = list(_SEARCH_NODES)
    if marker is not None:
        role, name = marker
        nodes.append(node("e99", "contentFrame", role, name))
    return Observation(nodes=nodes, url="http://x/content/search", title="Member Search")


def detail_screen(marker: tuple[str, str] | None = None) -> Observation:
    nodes = list(_DETAIL_NODES)
    if marker is not None:
        role, name = marker
        nodes.append(node("d99", "contentFrame", role, name))
    return Observation(nodes=nodes, url="http://x/content/detail", title="Member Detail")


def test_happy_path_reaches_success_and_extracts_the_output(member_balance_artifact):
    surface = ScriptedSurface([search_screen(), detail_screen()])
    surface.script("contentFrame", "e13", advance=True)  # click Search -> detail screen
    surface.script("contentFrame", "d7", result=ActionResult(ok=True, extracted_value="$4,231.50"))

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.SUCCESS
    assert result.outputs == {"balance_text": "$4,231.50"}
    assert not result.needs_escalation


@pytest.mark.parametrize(
    ("marker", "expected_status", "expected_code"),
    [
        (("generic", "No records match your search."), ReplayStatus.BUSINESS_OUTCOME, "MEMBER_NOT_FOUND"),
        (("heading", "Session Expired"), ReplayStatus.RECOVERABLE, "SESSION_EXPIRED"),
        (("heading", "Access Denied"), ReplayStatus.HARD_FAILURE, "ACCESS_DENIED"),
        (("heading", "Confirm"), ReplayStatus.RECOVERABLE, "UNEXPECTED_CONFIRM_DIALOG"),
    ],
)
def test_known_outcome_short_circuits_with_the_right_taxonomy(
    member_balance_artifact, marker, expected_status, expected_code
):
    surface = ScriptedSurface([search_screen(), search_screen(marker=marker)])
    surface.script("contentFrame", "e13", advance=True)  # click Search -> the faulted/alternate screen

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == expected_status
    assert result.outcome_code == expected_code
    # detected at the very next step's pre-check, before it touched anything
    assert result.failed_step_id == "extract_balance"
    assert result.outputs == {}
    assert result.needs_escalation is (expected_status != ReplayStatus.BUSINESS_OUTCOME)


def test_known_outcome_detected_only_at_the_final_checkpoint_check(member_balance_artifact):
    """The fault can also show up only *after* the last declared step
    ran cleanly -- e.g. the extract itself succeeds against a clean
    screen, and only the final post-loop re-observation lands on a
    screen that has since flipped to a fault."""
    surface = ScriptedSurface([search_screen(), detail_screen(), detail_screen(marker=("heading", "Access Denied"))])
    surface.script("contentFrame", "e13", advance=True)  # search screen -> clean detail screen
    surface.script(
        "contentFrame", "d7", result=ActionResult(ok=True, extracted_value="$4,231.50"), advance=True
    )  # clean detail -> detail-with-fault, but only after a successful extract

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.HARD_FAILURE
    assert result.outcome_code == "ACCESS_DENIED"
    assert result.failed_step_id == "extract_balance"  # the last declared step
    assert result.outputs == {"balance_text": "$4,231.50"}  # already-captured outputs are kept


def test_unrecognized_when_target_cannot_be_resolved(member_balance_artifact):
    """A search screen missing the textbox entirely: not a declared
    outcome, so the engine must not guess -- it escalates as
    unrecognized rather than silently skipping the step."""
    broken_screen = Observation(
        nodes=[
            node("e1", "contentFrame", "document"),
            node("e3", "contentFrame", "heading", "Member Search", parent_ref="e1", depth=1),
            node("e13", "contentFrame", "button", "Search", parent_ref="e1", depth=1),
        ],
        url="http://x/content/search",
        title="Member Search",
    )
    surface = ScriptedSurface([broken_screen])

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.UNRECOGNIZED
    assert result.failed_step_id == "type_member_id"
    assert "not_found" in result.reason
    assert result.needs_escalation


def test_unrecognized_when_target_is_ambiguous(member_balance_artifact):
    # a second, ambiguous "Search" button -- type_member_id still
    # resolves fine (label proximity, unaffected), but click_search's
    # only tier (ROLE_NAME, no fallback) is now ambiguous.
    screen = search_screen(marker=("button", "Search"))
    surface = ScriptedSurface([screen])

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.UNRECOGNIZED
    assert result.failed_step_id == "click_search"
    assert "ambiguous" in result.reason


# ---------------------------------------------------------------------------
# Retries: a minimal 2-step artifact dedicated to exercising max_retries
# ---------------------------------------------------------------------------


def _click_artifact(*, max_retries: int = 0, nav_max_retries: int = 0) -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="click_thing",
        version="1.0.0",
        description="Minimal artifact for retry/checkpoint tests.",
        tenant_scope=TenantScope(vendor_app_id="test_app"),
        steps=[
            Step(step_id="go", action=ActionType.NAVIGATE, literal_value="/x", max_retries=nav_max_retries),
            Step(
                step_id="click_btn",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("button", "Go")),
                max_retries=max_retries,
            ),
        ],
        checkpoint=Checkpoint(description="landed on Done", detection=role_tier("heading", "Done")),
        known_outcomes=[
            KnownOutcome(
                code="ACCESS_DENIED",
                description="no permission",
                category="hard_failure",
                detection=role_tier("heading", "Access Denied"),
            )
        ],
        policy_scope=PolicyScope(allowed_domains=["*"], allowed_action_types=[ActionType.NAVIGATE, ActionType.CLICK]),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


def _button_screen() -> Observation:
    return Observation(nodes=[node("b1", "main", "button", "Go")], url="http://x", title="Go")


def _done_screen() -> Observation:
    return Observation(nodes=[node("h1", "main", "heading", "Done")], url="http://x/done", title="Done")


def test_retry_recovers_on_a_later_attempt():
    artifact = _click_artifact(max_retries=1)
    surface = ScriptedSurface([_button_screen(), _done_screen()])
    surface.script(
        "main",
        "b1",
        results=[ActionResult(ok=False, error="timeout"), ActionResult(ok=True)],
        advance=True,
    )

    result = replay(artifact, {}, surface)

    assert result.status == ReplayStatus.SUCCESS
    assert len(surface.actions) == 3  # navigate + click's first (failed) attempt + its retry


def test_unrecognized_after_exhausting_retries():
    artifact = _click_artifact(max_retries=1)
    surface = ScriptedSurface([_button_screen(), _done_screen()])
    surface.script(
        "main",
        "b1",
        results=[ActionResult(ok=False, error="timeout"), ActionResult(ok=False, error="timeout")],
        advance=True,
    )

    result = replay(artifact, {}, surface)

    assert result.status == ReplayStatus.UNRECOGNIZED
    assert result.failed_step_id == "click_btn"
    assert "timeout" in result.reason
    assert len(surface.actions) == 3  # navigate + both click attempts


def test_checkpoint_not_confirmed_after_all_steps_succeed():
    artifact = _click_artifact()
    surface = ScriptedSurface([_button_screen(), Observation(nodes=[node("h1", "main", "heading", "Somewhere Else")], url="http://x", title="?")])
    surface.script("main", "b1", advance=True)

    result = replay(artifact, {}, surface)

    assert result.status == ReplayStatus.UNRECOGNIZED
    assert result.failed_step_id == "click_btn"
    assert "checkpoint" in result.reason


def test_navigate_failure_is_unrecognized_with_retries_applied():
    artifact = _click_artifact(nav_max_retries=2)
    surface = ScriptedSurface([_button_screen()])
    surface.script(None, None, result=ActionResult(ok=False, error="DNS error"), advance=False)

    result = replay(artifact, {}, surface)

    assert result.status == ReplayStatus.UNRECOGNIZED
    assert result.failed_step_id == "go"
    assert "DNS error" in result.reason
    assert len(surface.actions) == 3  # 1 + 2 retries


def test_navigate_retry_recovers_on_a_later_attempt():
    # two retries available (3 attempts), but the 2nd already succeeds --
    # exercises _act_with_retries' early `break`, not just exhaustion.
    artifact = _click_artifact(nav_max_retries=2)
    surface = ScriptedSurface([_button_screen(), _done_screen()])
    surface.script(None, None, results=[ActionResult(ok=False, error="blip"), ActionResult(ok=True)], advance=False)
    surface.script("main", "b1", advance=True)

    result = replay(artifact, {}, surface)

    assert result.status == ReplayStatus.SUCCESS
    assert len(surface.actions) == 3  # navigate's failed attempt + its (successful) retry + the click


class _FlakyResolutionSurface(ScriptedSurface):
    """A screen that briefly fails to resolve on its own, independent of
    any act() -- modeling a render that finishes a beat after the page
    loads (unlike ScriptedSurface's own advance-on-act model, which
    can't express 'the same navigation, observed twice, looks
    different')."""

    def __init__(self, first: Observation, later_screens: list[Observation]) -> None:
        super().__init__(later_screens)
        self._first = first
        self._observe_count = 0

    def observe(self) -> Observation:
        self._observe_count += 1
        return self._first if self._observe_count == 1 else super().observe()


def test_target_resolution_retry_recovers_on_a_later_attempt():
    artifact = _click_artifact(max_retries=1)
    empty_screen = Observation(nodes=[node("d1", "main", "document")], url="http://x", title="?")
    surface = _FlakyResolutionSurface(empty_screen, [_button_screen(), _done_screen()])
    surface.script("main", "b1", advance=True)

    result = replay(artifact, {}, surface)

    # click_btn resolves NOT_FOUND on the first (empty) observation, then
    # RESOLVED once the button has rendered on the retry's observation.
    assert result.status == ReplayStatus.SUCCESS


# ---------------------------------------------------------------------------
# The `guard` seam: cua.replay knows nothing about domains/risk levels,
# only about calling an injected PolicyGuard fresh before each step and
# honoring its verdict. cua.policy (Phase 6) supplies the real guard;
# here it's exercised with hand-written ones to prove the mechanism
# itself, independent of that module.
# ---------------------------------------------------------------------------


def test_guard_blocks_a_targeted_step_before_it_ever_reaches_the_surface(member_balance_artifact):
    surface = ScriptedSurface([search_screen()])

    def deny_click(step, observation):
        if step.step_id == "click_search":
            return PolicyDecision(allowed=False, reason="risky step not authorized")
        return PolicyDecision(allowed=True)

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface, guard=deny_click)

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "click_search"
    assert result.reason == "risky step not authorized"
    assert result.needs_escalation
    # the guard ran (and blocked) before the click itself was ever attempted
    assert all(a.ref != "e13" for a in surface.actions)


def test_guard_blocks_a_navigate_step_before_it_ever_reaches_the_surface():
    artifact = _click_artifact()
    surface = ScriptedSurface([_button_screen(), _done_screen()])

    def deny_everything(step, observation):
        return PolicyDecision(allowed=False, reason="off-allowlist domain")

    result = replay(artifact, {}, surface, guard=deny_everything)

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "go"
    assert result.reason == "off-allowlist domain"
    assert surface.actions == []  # not even the navigate was attempted


def test_guard_that_allows_everything_does_not_change_the_outcome(member_balance_artifact):
    surface = ScriptedSurface([search_screen(), detail_screen()])
    surface.script("contentFrame", "e13", advance=True)
    surface.script("contentFrame", "d7", result=ActionResult(ok=True, extracted_value="$4,231.50"))

    result = replay(
        member_balance_artifact,
        {"member_id": "10001"},
        surface,
        guard=lambda step, observation: PolicyDecision(allowed=True),
    )

    assert result.status == ReplayStatus.SUCCESS
    assert result.outputs == {"balance_text": "$4,231.50"}


def test_no_guard_means_no_policy_check_at_all(member_balance_artifact):
    """Default (guard=None) behavior is unchanged from before Phase 6:
    every existing test in this module already proves this, but this
    test says so explicitly."""
    surface = ScriptedSurface([search_screen(), detail_screen()])
    surface.script("contentFrame", "e13", advance=True)
    surface.script("contentFrame", "d7", result=ActionResult(ok=True, extracted_value="$4,231.50"))

    result = replay(member_balance_artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.SUCCESS


def test_boolean_input_is_stringified_lowercase_for_a_type_step():
    artifact = CapabilityArtifact(
        capability_id="type_thing",
        version="1.0.0",
        description="Minimal artifact for boolean-input stringification test.",
        tenant_scope=TenantScope(vendor_app_id="test_app"),
        input_schema=[ParamSpec(name="active", type=ParamType.BOOLEAN, required=True)],
        steps=[
            Step(step_id="go", action=ActionType.NAVIGATE, literal_value="/x"),
            Step(
                step_id="type_active",
                action=ActionType.TYPE,
                target=Target(primary=role_tier("textbox", "Active")),
                input_param="active",
            ),
        ],
        checkpoint=Checkpoint(description="typed", detection=role_tier("textbox", "Active")),
        policy_scope=PolicyScope(allowed_domains=["*"], allowed_action_types=[ActionType.NAVIGATE, ActionType.TYPE]),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )
    surface = ScriptedSurface([Observation(nodes=[node("t1", "main", "textbox", "Active")], url="http://x", title="?")])

    replay(artifact, {"active": True}, surface)

    type_action = next(a for a in surface.actions if a.ref == "t1")
    assert type_action.value == "true"
