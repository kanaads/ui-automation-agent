"""cua.policy.guard.build_default_guard: the real PolicyGuard built from
an artifact's own `policy_scope` (the domain allowlist) plus a
per-invocation set of step ids a human has explicitly authorized to run
despite being `RiskLevel.RISKY_IRREVERSIBLE`.

Exercised directly against the guard function -- no Surface, no
replay() -- so these prove the gating *logic* in isolation; test_enforce.py
proves it's actually wired into a replay run and test_engine_live.py
(tests/integration/policy) proves it against the real target app.
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
from cua.policy import build_default_guard
from cua.surface.models import Observation
from tests.unit.replay.conftest import node, role_tier

pytestmark = pytest.mark.unit


def _artifact(*, allowed_domains, risk=RiskLevel.SAFE, risk_rationale="") -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="thing",
        version="1.0.0",
        description="test",
        tenant_scope=TenantScope(vendor_app_id="test_app"),
        steps=[
            Step(step_id="go", action=ActionType.NAVIGATE, literal_value="/x"),
            Step(
                step_id="commit",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("button", "Confirm")),
                risk=risk,
                risk_rationale=risk_rationale,
            ),
        ],
        checkpoint=Checkpoint(description="done", detection=role_tier("heading", "Done")),
        policy_scope=PolicyScope(
            allowed_domains=allowed_domains, allowed_action_types=[ActionType.NAVIGATE, ActionType.CLICK]
        ),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


def _observation(url: str) -> Observation:
    return Observation(nodes=[node("b1", "main", "button", "Confirm")], url=url, title="?")


def test_allows_a_safe_step_on_an_allowed_domain():
    artifact = _artifact(allowed_domains=["example.com:8000"])
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[1], _observation("http://example.com:8000/x"))

    assert decision.allowed


def test_wildcard_domain_allows_anything():
    artifact = _artifact(allowed_domains=["*"])
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[0], _observation("http://anything.invalid/x"))

    assert decision.allowed


def test_blocks_when_the_observed_domain_is_not_on_the_allowlist():
    artifact = _artifact(allowed_domains=["example.com:8000"])
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[0], _observation("http://evil.example:9999/x"))

    assert not decision.allowed
    assert "evil.example:9999" in decision.reason


def test_blocks_a_risky_irreversible_step_by_default():
    artifact = _artifact(allowed_domains=["*"], risk=RiskLevel.RISKY_IRREVERSIBLE, risk_rationale="irreversibly commits money")
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[1], _observation("http://x/x"))

    assert not decision.allowed
    assert "commit" in decision.reason
    assert "risky_irreversible" in decision.reason


def test_allows_a_risky_irreversible_step_when_its_id_is_authorized():
    artifact = _artifact(allowed_domains=["*"], risk=RiskLevel.RISKY_IRREVERSIBLE, risk_rationale="irreversibly commits money")
    guard = build_default_guard(artifact, authorized_step_ids=frozenset({"commit"}))

    decision = guard(artifact.steps[1], _observation("http://x/x"))

    assert decision.allowed


def test_authorizing_a_different_step_id_does_not_authorize_this_one():
    artifact = _artifact(allowed_domains=["*"], risk=RiskLevel.RISKY_IRREVERSIBLE, risk_rationale="irreversibly commits money")
    guard = build_default_guard(artifact, authorized_step_ids=frozenset({"some_other_step"}))

    decision = guard(artifact.steps[1], _observation("http://x/x"))

    assert not decision.allowed


def test_a_safe_step_needs_no_authorization():
    artifact = _artifact(allowed_domains=["*"], risk=RiskLevel.SAFE)
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[1], _observation("http://x/x"))

    assert decision.allowed


def test_sensitive_risk_level_is_not_gated_only_risky_irreversible_is():
    artifact = _artifact(allowed_domains=["*"], risk=RiskLevel.SENSITIVE)
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[1], _observation("http://x/x"))

    assert decision.allowed


def test_domain_is_checked_before_risk_so_the_reason_is_specific():
    artifact = _artifact(allowed_domains=["example.com:8000"], risk=RiskLevel.RISKY_IRREVERSIBLE, risk_rationale="x")
    guard = build_default_guard(artifact)

    decision = guard(artifact.steps[1], _observation("http://evil.example:9999/x"))

    assert not decision.allowed
    assert "domain" in decision.reason.lower()
