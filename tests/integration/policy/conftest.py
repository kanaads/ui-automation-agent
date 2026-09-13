"""`build_open_subaccount_artifact()` models the target app's real
search -> detail -> open-sub-account -> confirm flow (see
cua.target_app.templates: detail_content.html's "Open Sub-Account"
link, subaccount_new.html's form, subaccount_confirm.html's final
"Confirm & Open Account" button).

The final CLICK step is tagged `risk=RiskLevel.RISKY_IRREVERSIBLE` --
per REPORT.md Section 2's own note on the target app, this is exactly
the action a recorded capability should stop short of by default: it
opens a real sub-account and there is no undo in this UI. That's what
makes it the right live capability to prove `cua.policy`'s gating
against a real target app rather than a fake one.
"""
from __future__ import annotations

from datetime import datetime, timezone

from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
    Checkpoint,
    ParamSpec,
    ParamType,
    PolicyScope,
    ProvenanceRecordedBy,
    RiskLevel,
    Step,
    Target,
    TenantScope,
)
from tests.unit.replay.conftest import label_tier, role_tier


def build_open_subaccount_artifact(*, allowed_domains: list[str] | None = None) -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="open_subaccount",
        version="1.0.0",
        description="Open a new sub-account for a member, given their ID, account type, initial deposit, and purpose.",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        input_schema=[
            ParamSpec(name="account_type", type=ParamType.STRING, required=True),
            ParamSpec(name="initial_deposit", type=ParamType.STRING, required=True),
            ParamSpec(name="purpose", type=ParamType.STRING, required=True),
        ],
        steps=[
            # A fixed member ("10001", the always-ACTIVE seeded member --
            # see cua.target_app.data) rather than a parameterized one:
            # this artifact exists to prove cua.policy's gating, not to
            # re-prove Phase 4/5's member lookup, so it skips straight
            # to the detail page a real search would have landed on.
            Step(step_id="go_to_detail", action=ActionType.NAVIGATE, literal_value="/app?start=/content/detail?id=10001"),
            Step(
                step_id="click_open_subaccount",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("link", "Open Sub-Account")),
            ),
            Step(
                step_id="select_account_type",
                action=ActionType.SELECT,
                target=Target(primary=label_tier("Account Type", "combobox")),
                input_param="account_type",
            ),
            Step(
                step_id="type_initial_deposit",
                action=ActionType.TYPE,
                target=Target(primary=label_tier("Initial Deposit", "textbox")),
                input_param="initial_deposit",
            ),
            Step(
                step_id="type_purpose",
                action=ActionType.TYPE,
                target=Target(primary=label_tier("Purpose", "textbox")),
                input_param="purpose",
            ),
            Step(
                step_id="click_continue",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("button", "Continue")),
            ),
            Step(
                step_id="click_confirm",
                action=ActionType.CLICK,
                target=Target(primary=role_tier("button", "Confirm & Open Account")),
                risk=RiskLevel.RISKY_IRREVERSIBLE,
                risk_rationale="Irreversibly opens a new sub-account and moves the initial deposit; there is no undo in this UI.",
            ),
        ],
        checkpoint=Checkpoint(description="Sub-account opened", detection=role_tier("heading", "Sub-Account Opened")),
        policy_scope=PolicyScope(
            allowed_domains=allowed_domains if allowed_domains is not None else ["*"],
            allowed_action_types=[ActionType.NAVIGATE, ActionType.CLICK, ActionType.SELECT, ActionType.TYPE],
        ),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )
