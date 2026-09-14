"""cua.evidence.capture: writes a genuine discovery or replay run to a
directory as reviewable evidence -- structured JSON plus a screenshot,
never just a status code. Deliberately does NOT reuse
`cua.policy.redact_result`'s masking for the discovery side (there is
no artifact/sensitive schema yet to mask against) or drop
`last_observation`/the transcript the way an escalation ticket does
(`cua.escalation.trigger`) -- an evidence bundle IS the trusted,
human-reviewer-facing sink those other modules are protecting *against*
leaking into, not another log/ticket queue one layer removed from a
human. It DOES reuse `redact_result` verbatim for the replay side,
since a real artifact's `sensitive` declarations must be honored
wherever its data lands, evidence directories included.
"""
import json
from datetime import datetime, timezone

import pytest

from cua.agent.contract import DiscoveryResult, DiscoveryStatus, DiscoveryStep
from cua.agent.decide import AgentDecision
from cua.artifact.models import (
    ActionType,
    CapabilityArtifact,
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
from cua.evidence.capture import save_discovery_evidence, save_replay_evidence
from cua.replay.contract import ReplayResult, ReplayStatus
from cua.surface.models import ActionResult, Observation, ObservedNode

pytestmark = pytest.mark.unit


def _observation(url: str = "http://x/content/search") -> Observation:
    return Observation(
        nodes=[
            ObservedNode(ref="e1", frame="contentFrame", role="textbox", name=None),
            ObservedNode(ref="e2", frame="contentFrame", role="button", name="Search"),
        ],
        url=url,
        title="Member Search",
    )


def _discovery_result(status: DiscoveryStatus = DiscoveryStatus.GOAL_REACHED) -> DiscoveryResult:
    decision = AgentDecision(thought="click search", action="click", frame="contentFrame", ref="e2")
    step = DiscoveryStep(decision=decision, observation=_observation(), action_result=ActionResult(ok=True))
    return DiscoveryResult(
        status=status,
        goal="look up member 10001",
        transcript=[step],
        reason="member detail is now showing" if status == DiscoveryStatus.GOAL_REACHED else "stuck",
        final_observation=_observation("http://x/content/detail"),
    )


def test_save_discovery_evidence_writes_run_json_with_the_given_metadata(tmp_path):
    result = _discovery_result()

    save_discovery_evidence(
        tmp_path, goal="look up member 10001", result=result, provider="bedrock", model="my-model"
    )

    run = json.loads((tmp_path / "run.json").read_text())
    assert run["goal"] == "look up member 10001"
    assert run["status"] == "goal_reached"
    assert run["succeeded"] is True
    assert run["provider"] == "bedrock"
    assert run["model"] == "my-model"
    assert run["steps_taken"] == 1
    assert "captured_at" in run


def test_save_discovery_evidence_writes_the_full_transcript(tmp_path):
    result = _discovery_result()

    save_discovery_evidence(tmp_path, goal="g", result=result, provider="bedrock", model="m")

    transcript = json.loads((tmp_path / "transcript.json").read_text())
    assert len(transcript) == 1
    assert transcript[0]["decision"]["action"] == "click"
    assert transcript[0]["decision"]["ref"] == "e2"
    assert transcript[0]["observation"]["url"] == "http://x/content/search"
    assert transcript[0]["observation"]["nodes"][1]["name"] == "Search"
    assert transcript[0]["action_result"]["ok"] is True


def test_save_discovery_evidence_writes_the_final_observation_separately(tmp_path):
    result = _discovery_result()

    save_discovery_evidence(tmp_path, goal="g", result=result, provider="bedrock", model="m")

    final = json.loads((tmp_path / "final_observation.json").read_text())
    assert final["url"] == "http://x/content/detail"


def test_save_discovery_evidence_writes_a_screenshot_when_given_one(tmp_path):
    result = _discovery_result()

    save_discovery_evidence(
        tmp_path, goal="g", result=result, provider="bedrock", model="m", screenshot=b"\x89PNGfakebytes"
    )

    assert (tmp_path / "final_screenshot.png").read_bytes() == b"\x89PNGfakebytes"


def test_save_discovery_evidence_omits_the_screenshot_file_when_none_given(tmp_path):
    result = _discovery_result()

    save_discovery_evidence(tmp_path, goal="g", result=result, provider="bedrock", model="m")

    assert not (tmp_path / "final_screenshot.png").exists()


def test_save_discovery_evidence_creates_the_output_directory(tmp_path):
    out = tmp_path / "nested" / "does_not_exist_yet"

    save_discovery_evidence(out, goal="g", result=_discovery_result(), provider="bedrock", model="m")

    assert (out / "run.json").exists()


@pytest.mark.parametrize("status", [DiscoveryStatus.STUCK, DiscoveryStatus.MAX_STEPS_EXCEEDED])
def test_save_discovery_evidence_records_an_unsuccessful_run_just_as_faithfully(tmp_path, status):
    result = _discovery_result(status)

    save_discovery_evidence(tmp_path, goal="g", result=result, provider="bedrock", model="m")

    run = json.loads((tmp_path / "run.json").read_text())
    assert run["succeeded"] is False
    assert run["status"] == status.value


def _artifact() -> CapabilityArtifact:
    return CapabilityArtifact(
        capability_id="look_up_member",
        version="1.0.0",
        description="d",
        tenant_scope=TenantScope(vendor_app_id="meridian_core"),
        input_schema=[ParamSpec(name="member_id", type=ParamType.STRING, required=True)],
        steps=[
            Step(
                step_id="s1",
                action=ActionType.TYPE,
                target=Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "textbox", "name": "x"})),
                input_param="member_id",
            )
        ],
        checkpoint=Checkpoint(
            description="d",
            detection=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "heading", "name": "Member Detail"}),
        ),
        policy_scope=PolicyScope(allowed_domains=["*"], allowed_action_types=[ActionType.TYPE]),
        provenance=ProvenanceRecordedBy(kind="llm_discovery", recorded_at=datetime.now(timezone.utc)),
    )


def test_save_replay_evidence_writes_a_redacted_result_json(tmp_path):
    result = ReplayResult(status=ReplayStatus.SUCCESS, outputs={"balance_text": "$4,231.50"})

    save_replay_evidence(tmp_path, artifact=_artifact(), raw_inputs={"member_id": "10001"}, result=result)

    written = json.loads((tmp_path / "result.json").read_text())
    assert written["status"] == "success"
    assert written["capability_id"] == "look_up_member"
    assert written["inputs"]["member_id"] == "10001"
    assert written["outputs"]["balance_text"] == "$4,231.50"
    assert "last_observation" not in written


def test_save_replay_evidence_redacts_sensitive_inputs_the_same_way_redact_result_does(tmp_path):
    artifact = _artifact()
    artifact = artifact.model_copy(
        update={"input_schema": [ParamSpec(name="member_id", type=ParamType.STRING, required=True, sensitive=True)]}
    )
    result = ReplayResult(status=ReplayStatus.SUCCESS)

    save_replay_evidence(tmp_path, artifact=artifact, raw_inputs={"member_id": "10001"}, result=result)

    written = json.loads((tmp_path / "result.json").read_text())
    assert written["inputs"]["member_id"] == "<redacted>"


def test_save_replay_evidence_writes_a_screenshot_when_given_one(tmp_path):
    result = ReplayResult(status=ReplayStatus.SUCCESS)

    save_replay_evidence(
        tmp_path, artifact=_artifact(), raw_inputs={"member_id": "10001"}, result=result, screenshot=b"pngbytes"
    )

    assert (tmp_path / "final_screenshot.png").read_bytes() == b"pngbytes"


def test_save_replay_evidence_creates_the_output_directory(tmp_path):
    out = tmp_path / "a" / "b"

    save_replay_evidence(out, artifact=_artifact(), raw_inputs={"member_id": "10001"}, result=ReplayResult(status=ReplayStatus.SUCCESS))

    assert (out / "result.json").exists()
