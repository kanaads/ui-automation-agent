"""cua.policy.guarded_replay: the one-call ergonomic wrapper around
cua.replay.replay() that supplies a real PolicyGuard (cua.policy.guard)
built from the artifact's own policy_scope plus whichever step ids THIS
invocation has been told are authorized. Exercised against a fake
Surface, mirroring the target app's real search -> detail ->
open-sub-account -> confirm flow (the confirm/commit step is the
RISKY_IRREVERSIBLE one -- see REPORT.md Section 2's own note that this
is exactly the action a recorded capability should stop short of by
default). tests/integration/policy proves the same shape against the
real live app.
"""
from datetime import datetime, timezone

import pytest

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    PolicyScope,
    ProvenanceRecordedBy,
    RiskLevel,
    Step,
    Target,
    TenantScope,
)
from cua.policy import guarded_replay
from cua.replay import ReplayStatus
from cua.surface.models import Observation
from tests.unit.replay.conftest import ScriptedSurface, node, role_tier

pytestmark = pytest.mark.unit


def _open_and_confirm_artifact(*, allowed_domains=("*",)) -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="open_subaccount",
        version="1.0.0",
        description="test",
        tenant_scope=TenantScope(vendor_app_id="test_app"),
        steps=[
            Step(step_id="go", action=ActionType.NAVIGATE, literal_value="/x"),
            Step(step_id="click_open", action=ActionType.CLICK, target=Target(primary=role_tier("link", "Open Sub-Account"))),
            Step(
                step_id="click_confirm",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("button", "Confirm & Open Account")),
                risk=RiskLevel.RISKY_IRREVERSIBLE,
                risk_rationale="irreversibly opens a new sub-account and cannot be undone via this UI",
            ),
        ],
        checkpoint=Checkpoint(description="account opened", detection=role_tier("heading", "Sub-Account Opened")),
        policy_scope=PolicyScope(
            allowed_domains=list(allowed_domains), allowed_action_types=[ActionType.NAVIGATE, ActionType.CLICK]
        ),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


def _open_screen() -> Observation:
    return Observation(nodes=[node("l1", "main", "link", "Open Sub-Account")], url="http://x/detail", title="?")


def _confirm_screen() -> Observation:
    return Observation(nodes=[node("b1", "main", "button", "Confirm & Open Account")], url="http://x/confirm", title="?")


def _success_screen() -> Observation:
    return Observation(nodes=[node("h1", "main", "heading", "Sub-Account Opened")], url="http://x/success", title="?")


def test_an_unauthorized_risky_step_is_blocked_and_never_reaches_the_surface():
    artifact = _open_and_confirm_artifact()
    surface = ScriptedSurface([_open_screen(), _confirm_screen()])
    surface.script("main", "l1", advance=True)

    result = guarded_replay(artifact, {}, surface)

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "click_confirm"
    assert result.needs_escalation
    assert all(a.ref != "b1" for a in surface.actions)


def test_authorizing_the_specific_step_id_lets_it_run_to_success():
    artifact = _open_and_confirm_artifact()
    surface = ScriptedSurface([_open_screen(), _confirm_screen(), _success_screen()])
    surface.script("main", "l1", advance=True)
    surface.script("main", "b1", advance=True)

    result = guarded_replay(artifact, {}, surface, authorized_step_ids=frozenset({"click_confirm"}))

    assert result.status == ReplayStatus.SUCCESS
    assert any(a.ref == "b1" for a in surface.actions)


def test_an_off_allowlist_domain_blocks_before_the_first_step():
    artifact = _open_and_confirm_artifact(allowed_domains=("allowed.example:8000",))
    surface = ScriptedSurface([_open_screen()])

    result = guarded_replay(artifact, {}, surface)

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "go"
    assert surface.actions == []


def test_authorizing_a_different_step_id_does_not_unblock_this_one():
    artifact = _open_and_confirm_artifact()
    surface = ScriptedSurface([_open_screen(), _confirm_screen()])
    surface.script("main", "l1", advance=True)

    result = guarded_replay(artifact, {}, surface, authorized_step_ids=frozenset({"some_other_step"}))

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "click_confirm"


def test_default_authorized_step_ids_is_empty_not_shared_mutable_state():
    """A frozenset() default is safe, but this pins it down explicitly:
    two independent calls with no authorization must not leak state."""
    artifact = _open_and_confirm_artifact()
    surface_a = ScriptedSurface([_open_screen(), _confirm_screen()])
    surface_a.script("main", "l1", advance=True)
    surface_b = ScriptedSurface([_open_screen(), _confirm_screen()])
    surface_b.script("main", "l1", advance=True)

    guarded_replay(artifact, {}, surface_a, authorized_step_ids=frozenset({"click_confirm"}))
    result_b = guarded_replay(artifact, {}, surface_b)

    assert result_b.status == ReplayStatus.POLICY_BLOCKED
