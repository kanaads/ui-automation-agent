"""Writes a genuine discovery or replay run to a directory as
reviewable evidence -- the assignment's Section 6 deliverable made
concrete: structured JSON plus a screenshot, never just a status code
in a terminal that vanishes when the run ends.

Deliberately NOT the same redaction posture as `cua.escalation.trigger`
or `cua.policy.redact_result`'s own callers: an evidence bundle written
here IS the trusted, human-reviewer-facing sink those other modules
protect *against* leaking into (a log aggregator, a ticket queue
visible to many operators) -- not another hop further from a human.
So `save_discovery_evidence` writes the full transcript and final
observation, verbatim, including the raw perception those other
modules deliberately drop. `save_replay_evidence` is the one exception:
it reuses `cua.policy.redact_result` verbatim rather than
re-implementing redaction, because a real artifact's own `sensitive`
declarations are a property of the *data*, not of which sink it lands
in -- they must be honored here exactly as they are in a log or a
ticket.

Screenshot redaction is out of scope here, same as everywhere else
this project mentions it (`CapabilityArtifact.to_log_safe_dict`,
`cua.policy.redact_result`): a `screenshot` argument is written
verbatim when given, never inspected or masked.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cua.agent.contract import DiscoveryResult
from cua.artifact.models import CapabilityArtifact
from cua.policy.redact import redact_result
from cua.replay.contract import ReplayResult


def save_discovery_evidence(
    out_dir: Path,
    *,
    goal: str,
    result: DiscoveryResult,
    provider: str,
    model: str,
    screenshot: bytes | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    run = {
        "goal": goal,
        "status": result.status.value,
        "succeeded": result.succeeded,
        "reason": result.reason,
        "steps_taken": len(result.transcript),
        "provider": provider,
        "model": model,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2))

    transcript = [
        {
            "decision": step.decision.model_dump(mode="json"),
            "observation": asdict(step.observation),
            "action_result": asdict(step.action_result),
        }
        for step in result.transcript
    ]
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2))

    if result.final_observation is not None:
        (out_dir / "final_observation.json").write_text(json.dumps(asdict(result.final_observation), indent=2))

    if screenshot is not None:
        (out_dir / "final_screenshot.png").write_bytes(screenshot)


def save_replay_evidence(
    out_dir: Path,
    *,
    artifact: CapabilityArtifact,
    raw_inputs: Mapping[str, Any],
    result: ReplayResult,
    screenshot: bytes | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    written = redact_result(artifact, raw_inputs, result)
    written["captured_at"] = datetime.now(timezone.utc).isoformat()
    (out_dir / "result.json").write_text(json.dumps(written, indent=2))

    if screenshot is not None:
        (out_dir / "final_screenshot.png").write_bytes(screenshot)
