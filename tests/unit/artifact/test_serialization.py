"""The artifact must be a serializable, versioned, reviewable contract:
- round-trips losslessly through JSON (it's what gets stored on disk / in
  a catalog and what a calling agent or human reviewer reads back),
- exports a real JSON Schema so a capability catalog or an agent's
  function-calling layer can validate invocations without bespoke code.
"""
import json

import pytest

from cua.artifact.models import CapabilityArtifact

pytestmark = pytest.mark.unit


def test_model_dump_json_round_trip(sample_artifact):
    dumped = sample_artifact.model_dump_json()
    restored = CapabilityArtifact.model_validate_json(dumped)
    assert restored == sample_artifact


def test_model_dump_mode_json_round_trip(sample_artifact):
    dumped = sample_artifact.model_dump(mode="json")
    restored = CapabilityArtifact.model_validate(dumped)
    assert restored == sample_artifact
    # must be plain-JSON-safe (no datetimes/enums left as Python objects)
    json.dumps(dumped)


def test_schema_version_is_present_and_pinned(sample_artifact):
    assert sample_artifact.schema_version == "1.0"


def test_json_schema_export_includes_top_level_contract_fields():
    schema = CapabilityArtifact.model_json_schema()
    assert schema["title"] == "CapabilityArtifact"
    for field in [
        "capability_id",
        "version",
        "input_schema",
        "output_schema",
        "steps",
        "checkpoint",
        "known_outcomes",
        "policy_scope",
        "provenance",
        "tenant_scope",
    ]:
        assert field in schema["properties"], f"missing {field} in exported JSON Schema"


def test_json_schema_export_is_valid_jsonschema_document(sample_artifact):
    """Not just present fields -- the exported schema must actually validate
    a real instance, since that's how a capability catalog / agent tool
    layer would use it."""
    import jsonschema

    schema = CapabilityArtifact.model_json_schema()
    instance = sample_artifact.model_dump(mode="json")
    jsonschema.validate(instance=instance, schema=schema)
