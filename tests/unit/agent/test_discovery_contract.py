import pytest

from cua.agent.contract import DiscoveryResult, DiscoveryStatus

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DiscoveryStatus.GOAL_REACHED, True),
        (DiscoveryStatus.STUCK, False),
        (DiscoveryStatus.MAX_STEPS_EXCEEDED, False),
    ],
)
def test_succeeded_matches_status(status, expected):
    assert DiscoveryResult(status=status, goal="g").succeeded is expected


def test_defaults_are_empty_not_none():
    result = DiscoveryResult(status=DiscoveryStatus.GOAL_REACHED, goal="g")
    assert result.transcript == []
    assert result.reason == ""


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DiscoveryStatus.GOAL_REACHED, False),
        (DiscoveryStatus.STUCK, True),
        (DiscoveryStatus.MAX_STEPS_EXCEEDED, True),
    ],
)
def test_needs_escalation_matches_status(status, expected):
    assert DiscoveryResult(status=status, goal="g").needs_escalation is expected
