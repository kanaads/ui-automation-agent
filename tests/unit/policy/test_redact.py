"""cua.policy.redact_result: a runtime-data analog of
CapabilityArtifact.to_log_safe_dict() (Phase 1). That one redacts the
recorded DOCUMENT (discovery-time DOM snippets baked into the
artifact); this one redacts what actually happened during ONE
invocation -- the raw inputs a caller supplied and the raw outputs a
run captured -- using the exact same `sensitive` declarations, so a
sensitive value never reaches a log/evidence sink in the clear just
because it came from a live run rather than the static artifact.
"""
from datetime import datetime, timezone

import pytest

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    OutputSpec,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    Step,
    Target,
    TenantScope,
)
from cua.policy import redact_result
from cua.replay import ReplayResult, ReplayStatus
from cua.surface.models import Observation
from tests.unit.replay.conftest import node, role_tier, type_step_using

pytestmark = pytest.mark.unit


def _artifact_with_sensitive_fields() -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="lookup_member",
        version="1.0.0",
        description="test",
        tenant_scope=TenantScope(vendor_app_id="test_app"),
        input_schema=[
            ParamSpec(name="member_id", type=ParamType.STRING, required=True),
            ParamSpec(name="pin", type=ParamType.STRING, required=True, sensitive=True),
        ],
        output_schema=[
            OutputSpec(name="balance_text", type=ParamType.STRING),
            OutputSpec(name="account_number", type=ParamType.STRING, sensitive=True),
        ],
        steps=[
            Step(step_id="go", action=ActionType.NAVIGATE, literal_value="/x"),
            type_step_using("member_id", step_id="type_member_id"),
            type_step_using("pin", step_id="type_pin"),
            Step(
                step_id="extract_balance",
                action=ActionType.EXTRACT,
                target=Target(primary=role_tier("cell", "Balance")),
                output_field="balance_text",
            ),
            Step(
                step_id="extract_account",
                action=ActionType.EXTRACT,
                target=Target(primary=role_tier("cell", "Account")),
                output_field="account_number",
            ),
        ],
        checkpoint=Checkpoint(description="done", detection=role_tier("heading", "Done")),
        policy_scope=PolicyScope(
            allowed_domains=["*"], allowed_action_types=[ActionType.NAVIGATE, ActionType.TYPE, ActionType.EXTRACT]
        ),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


def test_a_sensitive_input_is_masked():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(status=ReplayStatus.SUCCESS, outputs={"balance_text": "$10.00", "account_number": "SA-ABC123"})

    log_safe = redact_result(artifact, {"member_id": "10001", "pin": "1234"}, result)

    assert log_safe["inputs"] == {"member_id": "10001", "pin": "<redacted>"}


def test_a_sensitive_output_is_masked():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(status=ReplayStatus.SUCCESS, outputs={"balance_text": "$10.00", "account_number": "SA-ABC123"})

    log_safe = redact_result(artifact, {"member_id": "10001", "pin": "1234"}, result)

    assert log_safe["outputs"] == {"balance_text": "$10.00", "account_number": "<redacted>"}


def test_non_sensitive_fields_pass_through_unchanged():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(status=ReplayStatus.SUCCESS, outputs={"balance_text": "$10.00"})

    log_safe = redact_result(artifact, {"member_id": "10001", "pin": "1234"}, result)

    assert log_safe["inputs"]["member_id"] == "10001"
    assert log_safe["outputs"]["balance_text"] == "$10.00"


def test_status_and_failure_context_are_included():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(
        status=ReplayStatus.HARD_FAILURE, outcome_code="ACCESS_DENIED", failed_step_id="extract_balance", reason="no permission"
    )

    log_safe = redact_result(artifact, {"member_id": "10001", "pin": "1234"}, result)

    assert log_safe["capability_id"] == "lookup_member"
    assert log_safe["version"] == "1.0.0"
    assert log_safe["status"] == "hard_failure"
    assert log_safe["outcome_code"] == "ACCESS_DENIED"
    assert log_safe["failed_step_id"] == "extract_balance"
    assert log_safe["reason"] == "no permission"


def test_last_observation_is_never_included_even_when_present():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(
        status=ReplayStatus.SUCCESS,
        last_observation=Observation(nodes=[node("a1", "main", "cell", "1234-5678-9012")], url="http://x", title="?"),
    )

    log_safe = redact_result(artifact, {"member_id": "10001", "pin": "1234"}, result)

    assert "last_observation" not in log_safe


def test_an_input_never_supplied_is_simply_absent_not_a_redacted_placeholder():
    artifact = _artifact_with_sensitive_fields()
    result = ReplayResult(status=ReplayStatus.SUCCESS)

    log_safe = redact_result(artifact, {"member_id": "10001"}, result)

    assert log_safe["inputs"] == {"member_id": "10001"}
    assert "pin" not in log_safe["inputs"]
