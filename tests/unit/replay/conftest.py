"""Shared building blocks for cua.replay tests.

`build_member_balance_artifact()` builds a small, complete,
schema-valid CapabilityArtifact modeling the target app's real
search -> detail flow (look up a member, read their savings balance).
It is deliberately the SAME shape of artifact proven against the live
app in tests/integration/locator (Phase 4) and tests/integration/replay
(this phase) -- so the fixtures below don't just exercise invented
scenarios, they mirror a capability that was actually recorded against
the real hostile-legacy templates (see cua.target_app.templates).

`ScriptedSurface` is a fake `Surface` for unit-testing the engine
without a browser: a fixed sequence of `Observation` "screens" plus a
per-(frame, ref) script of what `act()` should do and whether the
action advances to the next screen -- deliberately explicit (default:
stay put) rather than inferring page transitions from the action type,
since WAIT_FOR/EXTRACT/ASSERT_CHECKPOINT don't navigate but CLICK
sometimes does and sometimes doesn't.
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
    Step,
    Target,
    TenantScope,
)
from cua.surface.base import Surface
from cua.surface.models import ActionResult, Observation, ObservedNode, SurfaceAction


def node(ref, frame, role, name=None, parent_ref=None, depth=0) -> ObservedNode:
    return ObservedNode(ref=ref, frame=frame, role=role, name=name, depth=depth, parent_ref=parent_ref)


def role_tier(role: str, name: str) -> LocatorTier:
    return LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": role, "name": name})


def label_tier(near_text: str, control_type: str) -> LocatorTier:
    return LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY, params={"near_text": near_text, "control_type": control_type}
    )


def type_step_using(input_param: str, *, step_id: str | None = None) -> Step:
    """A throwaway TYPE step that consumes `input_param` -- exists only
    to satisfy CapabilityArtifact's own 'every declared input is used by
    some step' rule when a test needs to declare an extra ParamSpec
    without it participating in the real search/detail flow."""
    return Step(
        step_id=step_id or f"type_{input_param}",
        action=ActionType.TYPE,
        target=Target(primary=role_tier("textbox", input_param)),
        input_param=input_param,
    )


def build_member_balance_artifact(
    *, extra_params: list[ParamSpec] | None = None, extra_steps: list[Step] | None = None
) -> CapabilityArtifact:
    steps = [
        # relative to an already-open session on the tenant's own origin
        # (see tests/integration/replay for the live proof) -- an
        # absolute URL would hardcode one tenant's domain into what is
        # otherwise a portable, tenant-agnostic capability (Section 4).
        # Targets the *shell* page (nav + content iframes), not the bare
        # content fragment directly, so "contentFrame" below is a real
        # named frame rather than the main document.
        Step(step_id="go_to_search", action=ActionType.NAVIGATE, literal_value="/app?start=/content/search"),
        Step(
            step_id="type_member_id",
            action=ActionType.TYPE,
            target=Target(primary=role_tier("textbox", "Member Number"), fallbacks=[label_tier("Member Number", "textbox")]),
            input_param="member_id",
        ),
        Step(step_id="click_search", action=ActionType.CLICK, target=Target(primary=role_tier("button", "Search"))),
        Step(
            step_id="extract_balance",
            action=ActionType.EXTRACT,
            target=Target(primary=label_tier("Savings Balance", "cell")),
            output_field="balance_text",
        ),
        *(extra_steps or []),
    ]
    return CapabilityArtifact(
        capability_id="get_member_balance",
        version="1.0.0",
        description="Look up a member by ID and read their savings balance.",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        input_schema=[ParamSpec(name="member_id", type=ParamType.STRING, required=True), *(extra_params or [])],
        output_schema=[OutputSpec(name="balance_text", type=ParamType.STRING)],
        steps=steps,
        checkpoint=Checkpoint(description="Member detail page is showing", detection=role_tier("heading", "Member Detail")),
        known_outcomes=[
            KnownOutcome(
                code="MEMBER_NOT_FOUND",
                description="No member matches the given ID",
                category="business_outcome",
                detection=role_tier("generic", "No records match your search."),
            ),
            KnownOutcome(
                code="SESSION_EXPIRED",
                description="The session expired mid-flow",
                category="recoverable",
                detection=role_tier("heading", "Session Expired"),
            ),
            KnownOutcome(
                code="ACCESS_DENIED",
                description="The account lacks permission to view this record",
                category="hard_failure",
                detection=role_tier("heading", "Access Denied"),
            ),
            KnownOutcome(
                code="UNEXPECTED_CONFIRM_DIALOG",
                description="An unrelated confirmation interstitial appeared",
                category="recoverable",
                detection=role_tier("heading", "Confirm"),
            ),
        ],
        policy_scope=PolicyScope(
            allowed_domains=["*"],
            allowed_action_types=[ActionType.NAVIGATE, ActionType.TYPE, ActionType.CLICK, ActionType.EXTRACT],
        ),
        provenance=ProvenanceRecordedBy(kind="human_authored", recorded_at=datetime.now(timezone.utc)),
    )


@pytest.fixture()
def member_balance_artifact() -> CapabilityArtifact:
    return build_member_balance_artifact()


class ScriptedSurface(Surface):
    """A fake Surface driven by a fixed list of `Observation` screens.

    `observe()` always returns `screens[pointer]`. `act()` looks up a
    canned outcome for `(action.frame, action.ref)`; if none was
    scripted, it defaults to `ActionResult(ok=True)` *without* advancing
    -- an unscripted action succeeding-but-going-nowhere is a safer
    default for a test to silently get than an unscripted action
    silently skipping a screen. Every call to `act()` is recorded in
    `.actions` so tests can assert retry counts.
    """

    def __init__(self, screens: list[Observation]) -> None:
        self._screens = screens
        self._pointer = 0
        self._script: dict[tuple[str | None, str | None], list[tuple[ActionResult, bool]]] = {}
        self.actions: list[SurfaceAction] = []

    def script(
        self,
        frame: str | None,
        ref: str | None,
        *,
        result: ActionResult | None = None,
        results: list[ActionResult] | None = None,
        advance: bool = True,
    ) -> None:
        """Queue what `act()` should do for this (frame, ref). Pass either
        a single `result` (repeats forever) or `results` (consumed in
        order, the last one repeating once exhausted) -- the latter is
        what lets a test simulate 'fails once, then recovers on retry'.
        """
        outcomes = results if results is not None else [result or ActionResult(ok=True)]
        self._script[(frame, ref)] = [(outcome, advance) for outcome in outcomes]

    def observe(self) -> Observation:
        return self._screens[self._pointer]

    def act(self, action: SurfaceAction) -> ActionResult:
        self.actions.append(action)
        queue = self._script.get((action.frame, action.ref))
        if not queue:
            return ActionResult(ok=True)
        result, advance = queue[0] if len(queue) == 1 else queue.pop(0)
        if result.ok and advance and self._pointer < len(self._screens) - 1:
            self._pointer += 1
        return result

    def screenshot(self) -> bytes:
        return b""

    def current_url(self) -> str:
        return self._screens[self._pointer].url
