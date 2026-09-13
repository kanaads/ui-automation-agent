"""End-to-end proof that Phase 1 -> Phase 3 -> Phase 4 -> Phase 5 fit
together for real: the exact `member_balance_artifact` fixture used
against synthetic screens in tests/unit/replay is replayed here with a
real WebSurface against a real, running instance of the target app --
including genuine fault injection via the same FaultController proven
in Phase 2, not a simulated equivalent.
"""
import pytest

from cua.replay import ReplayStatus, replay
from cua.surface.web import WebSurface
from tests.integration.replay.conftest import arm_fault
from tests.unit.replay.conftest import build_member_balance_artifact

pytestmark = pytest.mark.integration


def test_happy_path_reaches_success_and_extracts_the_real_balance_live(seeded_page, live_app):
    seeded_page.goto(f"{live_app}/nav")  # an already-open session on the tenant's origin
    surface = WebSurface(seeded_page)
    artifact = build_member_balance_artifact()

    result = replay(artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.SUCCESS
    assert result.outputs == {"balance_text": "$4,231.50"}
    assert not result.needs_escalation


def test_member_not_found_is_a_business_outcome_live(seeded_page, live_app):
    seeded_page.goto(f"{live_app}/nav")
    surface = WebSurface(seeded_page)
    artifact = build_member_balance_artifact()

    result = replay(artifact, {"member_id": "99999"}, surface)

    assert result.status == ReplayStatus.BUSINESS_OUTCOME
    assert result.outcome_code == "MEMBER_NOT_FOUND"
    assert result.outputs == {}
    assert not result.needs_escalation


def test_session_timeout_fault_is_classified_recoverable_live(seeded_page, sid, live_app):
    arm_fault(live_app, sid, "search", "session_timeout")
    seeded_page.goto(f"{live_app}/nav")
    surface = WebSurface(seeded_page)
    artifact = build_member_balance_artifact()

    result = replay(artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.RECOVERABLE
    assert result.outcome_code == "SESSION_EXPIRED"
    assert result.needs_escalation


def test_permission_denied_fault_is_classified_hard_failure_live(seeded_page, sid, live_app):
    arm_fault(live_app, sid, "detail", "permission_denied")
    seeded_page.goto(f"{live_app}/nav")
    surface = WebSurface(seeded_page)
    artifact = build_member_balance_artifact()

    result = replay(artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.HARD_FAILURE
    assert result.outcome_code == "ACCESS_DENIED"
    assert result.needs_escalation


def test_surprise_dialog_fault_is_classified_recoverable_live(seeded_page, sid, live_app):
    arm_fault(live_app, sid, "search", "surprise_dialog")
    seeded_page.goto(f"{live_app}/nav")
    surface = WebSurface(seeded_page)
    artifact = build_member_balance_artifact()

    result = replay(artifact, {"member_id": "10001"}, surface)

    assert result.status == ReplayStatus.RECOVERABLE
    assert result.outcome_code == "UNEXPECTED_CONFIRM_DIALOG"
