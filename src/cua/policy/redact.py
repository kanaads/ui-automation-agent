"""A runtime-data analog of `CapabilityArtifact.to_log_safe_dict()`
(Phase 1). That one redacts the recorded DOCUMENT (discovery-time DOM
snippets baked into the artifact itself); this one redacts what
actually happened during ONE invocation -- the raw inputs a caller
supplied and the raw outputs a run captured -- using the exact same
`sensitive` declarations on `ParamSpec`/`OutputSpec`, so a sensitive
value never reaches a log/evidence sink in the clear just because it
came from a live run rather than the static artifact.

`last_observation` is deliberately dropped entirely, not masked field
by field: an `Observation`'s accessible-name text has no declared
field boundary to redact against -- the same reasoning
`to_log_safe_dict`'s own docstring gives for leaving screenshot
redaction to a lower layer (`cua.evidence`). Documented as a deliberate
cut in REPORT.md Section 7, not an oversight.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cua.artifact.models import CapabilityArtifact
from cua.replay.contract import ReplayResult

_REDACTED = "<redacted>"


def redact_result(
    artifact: CapabilityArtifact, raw_inputs: Mapping[str, Any], result: ReplayResult
) -> dict[str, Any]:
    sensitive_names = {p.name for p in artifact.input_schema if p.sensitive} | {
        o.name for o in artifact.output_schema if o.sensitive
    }
    return {
        "capability_id": artifact.capability_id,
        "version": artifact.version,
        "status": result.status.value,
        "outcome_code": result.outcome_code,
        "failed_step_id": result.failed_step_id,
        "reason": result.reason,
        "inputs": {name: (_REDACTED if name in sensitive_names else value) for name, value in raw_inputs.items()},
        "outputs": {
            name: (_REDACTED if name in sensitive_names else value) for name, value in result.outputs.items()
        },
    }
