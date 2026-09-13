"""Shared fixtures for artifact schema tests.

The fixture builder produces a realistic, fully valid CapabilityArtifact for
the "look up member and read savings balance" flow described in the
assignment brief. Individual tests mutate a copy of these kwargs to exercise
one validation rule at a time, which keeps each test's intent obvious.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    KnownOutcome,
    LocatorStrategy,
    LocatorTier,
    OutputSpec,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    RecordedEvidence,
    RiskLevel,
    Step,
    Target,
    TenantScope,
)


def role_locator(role: str, name: str) -> LocatorTier:
    return LocatorTier(
        strategy=LocatorStrategy.ROLE_NAME,
        params={"role": role, "name": name},
        confidence_rationale=f"Stable accessible role+name for '{name}'.",
    )


def label_proximity_locator(near_text: str, control_type: str) -> LocatorTier:
    return LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY,
        params={"near_text": near_text, "control_type": control_type},
        confidence_rationale=f"Falls back to the control nearest the '{near_text}' label.",
    )


def valid_artifact_kwargs() -> dict:
    """Return kwargs for a fully valid CapabilityArtifact.

    Flow: navigate to search -> type member_id -> click search ->
    checkpoint (detail page loaded) -> extract savings_balance and
    member_name. Includes one declared business outcome (not found).
    """
    search_target = Target(
        primary=role_locator("textbox", "Member Number"),
        fallbacks=[label_proximity_locator("Member Number", "textbox")],
    )
    search_button_target = Target(
        primary=role_locator("button", "Search"),
        fallbacks=[label_proximity_locator("Member Number", "button")],
    )
    balance_target = Target(
        primary=role_locator("cell", "Savings Balance"),
        fallbacks=[label_proximity_locator("Savings Balance", "cell")],
        recorded_evidence=RecordedEvidence(
            bbox=(402, 230, 60, 22),
            screenshot_ref="step_03.png",
            dom_hint="td.balance-cell",
        ),
    )
    name_target = Target(
        primary=role_locator("cell", "Member Name"),
        fallbacks=[label_proximity_locator("Member Name", "cell")],
    )
    not_found_detector = LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY,
        params={"near_text": "No records match", "control_type": "text"},
        confidence_rationale="Legacy app renders this exact banner text on a miss.",
    )
    checkpoint_detector = role_locator("heading", "Member Detail")

    steps = [
        Step(
            step_id="s1_navigate",
            action=ActionType.NAVIGATE,
            literal_value="/members/search",
            risk=RiskLevel.SAFE,
        ),
        Step(
            step_id="s2_type_member_id",
            action=ActionType.TYPE,
            target=search_target,
            input_param="member_id",
            risk=RiskLevel.SAFE,
        ),
        Step(
            step_id="s3_click_search",
            action=ActionType.CLICK,
            target=search_button_target,
            risk=RiskLevel.SAFE,
        ),
        Step(
            step_id="s4_extract_balance",
            action=ActionType.EXTRACT,
            target=balance_target,
            output_field="savings_balance",
            risk=RiskLevel.SAFE,
        ),
        Step(
            step_id="s5_extract_name",
            action=ActionType.EXTRACT,
            target=name_target,
            output_field="member_name",
            risk=RiskLevel.SAFE,
        ),
    ]

    return {
        "capability_id": "lookup_member_savings_balance",
        "version": "1.0.0",
        "description": (
            "Look up a credit union member by member number and read their "
            "current savings balance and display name."
        ),
        "tenant_scope": TenantScope(vendor_app_id="meridian_core"),
        "input_schema": [
            ParamSpec(
                name="member_id",
                type=ParamType.STRING,
                pattern=r"^\d{5,10}$",
                description="Credit union member number.",
            ),
        ],
        "output_schema": [
            OutputSpec(name="savings_balance", type=ParamType.NUMBER, sensitive=True),
            OutputSpec(name="member_name", type=ParamType.STRING, sensitive=True),
        ],
        "steps": steps,
        "checkpoint": Checkpoint(
            description="Member detail page has loaded for the searched member.",
            detection=checkpoint_detector,
        ),
        "known_outcomes": [
            KnownOutcome(
                code="MEMBER_NOT_FOUND",
                description="No member matches the given member number.",
                category="business_outcome",
                detection=not_found_detector,
            ),
        ],
        "policy_scope": PolicyScope(
            allowed_domains=["localhost:8000"],
            allowed_action_types=[
                ActionType.NAVIGATE,
                ActionType.TYPE,
                ActionType.CLICK,
                ActionType.EXTRACT,
            ],
        ),
        "provenance": ProvenanceRecordedBy(
            kind="llm_discovery",
            model="llama-3.1-70b-versatile",
            discovery_run_id="run_20260101_000000",
            recorded_at=datetime.now(timezone.utc),
        ),
    }


@pytest.fixture()
def artifact_kwargs() -> dict:
    return valid_artifact_kwargs()


@pytest.fixture()
def sample_artifact(artifact_kwargs: dict) -> CapabilityArtifact:
    return CapabilityArtifact(**artifact_kwargs)
