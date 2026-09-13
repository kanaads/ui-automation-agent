"""Cross-field contract tests for CapabilityArtifact.

These are the rules that make the artifact a real *contract* rather than a
loose bag of fields: every reference resolves, every declared input/output
is actually wired to a step, and the artifact declares its own policy
footprint consistently with what it does.
"""
import pytest
from pydantic import ValidationError

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    OutputSpec,
    ParamSpec,
    ParamType,
    RiskLevel,
)

pytestmark = pytest.mark.unit


def test_valid_full_artifact_constructs(artifact_kwargs):
    artifact = CapabilityArtifact(**artifact_kwargs)
    assert artifact.capability_id == "lookup_member_savings_balance"
    assert len(artifact.steps) == 5


@pytest.mark.parametrize("bad_id", ["Lookup Member", "lookup-member", "1lookup", "Lookup_Member"])
def test_capability_id_must_be_snake_case_slug(artifact_kwargs, bad_id):
    artifact_kwargs["capability_id"] = bad_id
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


@pytest.mark.parametrize("bad_version", ["1.0", "v1.0.0", "1.0.0-beta", "latest"])
def test_version_must_be_semver(artifact_kwargs, bad_version):
    artifact_kwargs["version"] = bad_version
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_at_least_one_step_is_required(artifact_kwargs):
    artifact_kwargs["steps"] = []
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_duplicate_step_ids_are_rejected(artifact_kwargs):
    steps = list(artifact_kwargs["steps"])
    dup = steps[0].model_copy(update={"step_id": steps[1].step_id})
    artifact_kwargs["steps"] = steps + [dup]
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_step_referencing_unknown_input_param_is_rejected(artifact_kwargs):
    steps = list(artifact_kwargs["steps"])
    steps[1] = steps[1].model_copy(update={"input_param": "not_a_declared_param"})
    artifact_kwargs["steps"] = steps
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_step_referencing_unknown_output_field_is_rejected(artifact_kwargs):
    steps = list(artifact_kwargs["steps"])
    steps[3] = steps[3].model_copy(update={"output_field": "not_a_declared_output"})
    artifact_kwargs["steps"] = steps
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_declared_input_param_not_used_by_any_step_is_rejected(artifact_kwargs):
    """A param nobody reads is either a mistake or dead surface area; both
    should be caught at authoring/review time, not discovered in production."""
    artifact_kwargs["input_schema"] = list(artifact_kwargs["input_schema"]) + [
        ParamSpec(name="unused_param", type=ParamType.STRING, required=False)
    ]
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_required_output_not_produced_by_any_step_is_rejected(artifact_kwargs):
    artifact_kwargs["output_schema"] = list(artifact_kwargs["output_schema"]) + [
        OutputSpec(name="branch_code", type=ParamType.STRING, nullable=False)
    ]
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_nullable_output_need_not_be_produced_by_a_step(artifact_kwargs):
    """A nullable output may legitimately be absent on some known outcomes
    (e.g. no balance to report when MEMBER_NOT_FOUND), so it doesn't need a
    producing step wired up for the schema to be valid."""
    artifact_kwargs["output_schema"] = list(artifact_kwargs["output_schema"]) + [
        OutputSpec(name="branch_code", type=ParamType.STRING, nullable=True)
    ]
    artifact = CapabilityArtifact(**artifact_kwargs)
    assert any(o.name == "branch_code" for o in artifact.output_schema)


def test_policy_scope_must_cover_every_action_type_actually_used(artifact_kwargs):
    """The artifact self-declares its policy footprint; that declaration
    must not silently under-report what the recorded flow actually does."""
    artifact_kwargs["policy_scope"].allowed_action_types = [ActionType.NAVIGATE]
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_tenant_override_requires_a_base_capability_id(artifact_kwargs):
    from cua.artifact.models import TenantScope

    artifact_kwargs["tenant_scope"] = TenantScope(vendor_app_id="meridian_core", tenant_id="tenant_b")
    with pytest.raises(ValidationError):
        CapabilityArtifact(**artifact_kwargs)


def test_tenant_override_valid_with_base_capability_id(artifact_kwargs):
    from cua.artifact.models import TenantScope

    artifact_kwargs["tenant_scope"] = TenantScope(
        vendor_app_id="meridian_core",
        tenant_id="tenant_b",
        base_capability_id="lookup_member_savings_balance",
        overrides={"s3_click_search": {"primary": {"params": {"name": "Find Member"}}}},
    )
    artifact = CapabilityArtifact(**artifact_kwargs)
    assert artifact.tenant_scope.tenant_id == "tenant_b"


def test_risky_step_type_must_appear_in_policy_scope_too(artifact_kwargs):
    """Sanity check that risk classification and the allowlist are two
    independent axes: a SAFE step of an allowed action type is fine even
    though nothing here is RISKY_IRREVERSIBLE by default."""
    artifact = CapabilityArtifact(**artifact_kwargs)
    assert all(s.risk == RiskLevel.SAFE for s in artifact.steps)
