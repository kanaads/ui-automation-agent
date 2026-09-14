"""cua.escalation.trigger: the glue turning an escalating ReplayResult
or DiscoveryResult into a HandoffTicket ready to `queue.open()`. Both
functions return None outright for a non-escalating result -- there is
nothing to raise a ticket about, and "None means don't escalate" is a
plainer contract for a caller than an empty/sentinel ticket would be.
"""
from datetime import datetime, timezone

import pytest

from cua.agent.contract import DiscoveryResult, DiscoveryStatus
from cua.artifact.models import (
    ActionType,
    Checkpoint,
    LocatorStrategy,
    LocatorTier,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    Step,
    Target,
    TenantScope,
)
from cua.escalation.contract import HandoffSource, HandoffStatus, SessionHandle
from cua.escalation.trigger import ticket_from_discovery, ticket_from_replay
from cua.replay.contract import ReplayResult, ReplayStatus

pytestmark = pytest.mark.unit


def _artifact() -> object:
    from cua.artifact.models import CapabilityArtifact

    return CapabilityArtifact(
        capability_id="open_subaccount",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        input_schema=[ParamSpec(name="ssn", type=ParamType.STRING, sensitive=True)],
        steps=[
            Step(
                step_id="s1",
                action=ActionType.TYPE,
                target=Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "textbox", "name": "SSN"})),
                input_param="ssn",
            )
        ],
        checkpoint=Checkpoint(
            description="done", detection=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "heading", "name": "Done"})
        ),
        policy_scope=PolicyScope(allowed_domains=["*"], allowed_action_types=[ActionType.TYPE]),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


@pytest.mark.parametrize("status", [ReplayStatus.SUCCESS, ReplayStatus.BUSINESS_OUTCOME])
def test_ticket_from_replay_returns_none_when_no_escalation_is_needed(status):
    result = ReplayResult(status=status)

    assert ticket_from_replay(result, artifact=_artifact(), raw_inputs={"ssn": "123-45-6789"}, session=SessionHandle()) is None


@pytest.mark.parametrize(
    "status", [ReplayStatus.RECOVERABLE, ReplayStatus.HARD_FAILURE, ReplayStatus.UNRECOGNIZED, ReplayStatus.POLICY_BLOCKED]
)
def test_ticket_from_replay_builds_an_open_ticket_for_every_escalating_status(status):
    result = ReplayResult(status=status, failed_step_id="s1", reason="something went wrong")

    ticket = ticket_from_replay(result, artifact=_artifact(), raw_inputs={"ssn": "123-45-6789"}, session=SessionHandle())

    assert ticket is not None
    assert ticket.status == HandoffStatus.OPEN
    assert ticket.source == HandoffSource.REPLAY
    assert ticket.status_code == status.value
    assert ticket.reason == "something went wrong"
    assert ticket.capability_id == "open_subaccount"


def test_ticket_from_replay_context_is_redacted_the_same_way_redact_result_is():
    """Reuses cua.policy.redact_result rather than re-implementing
    redaction -- the sensitive ssn input must never reach the ticket in
    the clear, and last_observation must never appear at all."""
    result = ReplayResult(
        status=ReplayStatus.HARD_FAILURE,
        last_observation=None,
    )

    ticket = ticket_from_replay(result, artifact=_artifact(), raw_inputs={"ssn": "123-45-6789"}, session=SessionHandle())

    assert ticket.context["inputs"]["ssn"] == "<redacted>"
    assert "last_observation" not in ticket.context


def test_ticket_from_replay_carries_the_given_session_handle():
    session = SessionHandle(cdp_endpoint="http://127.0.0.1:9333", page_marker="abc123")
    result = ReplayResult(status=ReplayStatus.POLICY_BLOCKED)

    ticket = ticket_from_replay(result, artifact=_artifact(), raw_inputs={}, session=session)

    assert ticket.session == session


def test_ticket_from_replay_generates_a_fresh_id_each_call():
    result = ReplayResult(status=ReplayStatus.POLICY_BLOCKED)

    t1 = ticket_from_replay(result, artifact=_artifact(), raw_inputs={}, session=SessionHandle())
    t2 = ticket_from_replay(result, artifact=_artifact(), raw_inputs={}, session=SessionHandle())

    assert t1.ticket_id != t2.ticket_id


def test_ticket_from_discovery_returns_none_when_goal_was_reached():
    result = DiscoveryResult(status=DiscoveryStatus.GOAL_REACHED, goal="look up member 10001")

    assert ticket_from_discovery(result, session=SessionHandle()) is None


@pytest.mark.parametrize("status", [DiscoveryStatus.STUCK, DiscoveryStatus.MAX_STEPS_EXCEEDED])
def test_ticket_from_discovery_builds_an_open_ticket_for_every_escalating_status(status):
    result = DiscoveryResult(status=status, goal="look up member 10001", reason="no visible way to proceed")

    ticket = ticket_from_discovery(result, session=SessionHandle())

    assert ticket is not None
    assert ticket.status == HandoffStatus.OPEN
    assert ticket.source == HandoffSource.DISCOVERY
    assert ticket.status_code == status.value
    assert ticket.reason == "no visible way to proceed"
    assert ticket.capability_id is None


def test_ticket_from_discovery_context_never_leaks_the_observation():
    """Discovery has no artifact/sensitive-field schema to redact
    against yet (that's exactly why a human is being looped in) -- so
    the context is kept to non-content metadata only, the same
    "never include the raw perception" rule redact_result applies once
    an artifact does exist."""
    result = DiscoveryResult(status=DiscoveryStatus.STUCK, goal="look up member 10001", reason="r")

    ticket = ticket_from_discovery(result, session=SessionHandle())

    assert ticket.context["goal"] == "look up member 10001"
    assert "final_observation" not in ticket.context
    assert "transcript" not in ticket.context
