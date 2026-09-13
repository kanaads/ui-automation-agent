"""The result contract itself: a ReplayResult's status determines whether
a caller (the agent loop, eventually the escalation layer) must stop and
hand off to a human, or can treat the invocation as finished."""
import pytest

from cua.replay.contract import PolicyDecision, ReplayResult, ReplayStatus

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ReplayStatus.SUCCESS, False),
        (ReplayStatus.BUSINESS_OUTCOME, False),
        (ReplayStatus.RECOVERABLE, True),
        (ReplayStatus.HARD_FAILURE, True),
        (ReplayStatus.UNRECOGNIZED, True),
        (ReplayStatus.POLICY_BLOCKED, True),
    ],
)
def test_needs_escalation_matches_status(status, expected):
    assert ReplayResult(status=status).needs_escalation is expected


def test_defaults_are_empty_not_none():
    result = ReplayResult(status=ReplayStatus.SUCCESS)
    assert result.outputs == {}
    assert result.outcome_code is None
    assert result.failed_step_id is None
    assert result.reason == ""
    assert result.last_observation is None


def test_policy_decision_defaults_to_no_reason():
    assert PolicyDecision(allowed=True).reason == ""


def test_policy_decision_carries_its_reason():
    decision = PolicyDecision(allowed=False, reason="off-allowlist domain")
    assert decision.allowed is False
    assert decision.reason == "off-allowlist domain"
