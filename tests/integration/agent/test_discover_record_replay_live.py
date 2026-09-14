"""The full discover -> record -> replay pipeline, proven end-to-end
against the REAL target app: a live LLM-driven discovery run produces
a transcript, `cua.agent.recorder.build_artifact_from_discovery` turns
that transcript into a `CapabilityArtifact`, and `cua.replay.replay`
executes THAT artifact -- deterministically, no LLM involved -- on a
second, independent page and reaches `SUCCESS`.

This is the strongest proof available that `infer_target`'s output is
genuinely replayable, not just structurally valid: a Target built from
one recorded (frame, ref) pair has to resolve correctly against a
freshly rendered instance of the same page, on a different page object
entirely, with a different member id supplied as a real parameter --
never the literal value discovery happened to type.
"""
from datetime import datetime, timezone

import pytest

from cua.agent.contract import DiscoveryStatus
from cua.agent.discover import discover
from cua.agent.recorder import build_artifact_from_discovery
from cua.artifact.models import (
    ActionType,
    Checkpoint,
    LocatorStrategy,
    LocatorTier,
    ParamSpec,
    ParamType,
    ProvenanceRecordedBy,
    TenantScope,
)
from cua.replay import ReplayStatus, replay
from cua.surface.web import WebSurface
from tests.integration.agent.conftest import SearchFromScratchScript

pytestmark = pytest.mark.integration


def test_discover_then_record_then_replay_reaches_success_on_a_fresh_page(live_app, browser):
    discovery_page = browser.new_page()
    try:
        discovery_surface = WebSurface(discovery_page)
        llm = SearchFromScratchScript(discovery_surface, start_url=f"{live_app}/app", member_id="10001")

        result = discover("Look up member 10001 and open their detail page.", discovery_surface, llm)
        assert result.status == DiscoveryStatus.GOAL_REACHED
    finally:
        discovery_page.close()

    artifact = build_artifact_from_discovery(
        result,
        capability_id="look_up_member",
        version="1.0.0",
        description="Look up a member by id and open their detail page.",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        checkpoint=Checkpoint(
            description="The member detail page is showing.",
            detection=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "heading", "name": "Member Detail"}),
        ),
        input_schema=[ParamSpec(name="member_id", type=ParamType.STRING, required=True)],
        parameterize={"10001": "member_id"},
        provenance=ProvenanceRecordedBy(kind="llm_discovery", discovery_run_id="test-run-1", recorded_at=datetime.now(timezone.utc)),
    )

    # The recorded transcript starts with the navigate discover() issued
    # itself, so the artifact stands on its own -- no assumption that a
    # fresh Surface is already sitting on the right page.
    assert artifact.steps[0].action == ActionType.NAVIGATE
    assert [s.action for s in artifact.steps] == [ActionType.NAVIGATE, ActionType.TYPE, ActionType.CLICK]
    # The typed value was correctly recognized as the thing being
    # parameterized, not baked in as a literal that would only ever
    # look up member 10001 again.
    type_step = artifact.steps[1]
    assert type_step.input_param == "member_id"
    assert type_step.literal_value is None

    replay_page = browser.new_page()
    try:
        replay_surface = WebSurface(replay_page)
        # A different member id than the one discovery happened to use --
        # proves the artifact generalizes, not just replays discovery's
        # own literal input back at itself.
        replay_result = replay(artifact, {"member_id": "10002"}, replay_surface)

        assert replay_result.status == ReplayStatus.SUCCESS, replay_result.reason
    finally:
        replay_page.close()
