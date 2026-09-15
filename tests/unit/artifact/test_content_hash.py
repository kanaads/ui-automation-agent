"""content_hash seal: every CapabilityArtifact carries a SHA-256 digest of
its canonical payload (everything except the hash field itself). Fresh
construction seals automatically; a present digest is verified on load
so a tampered or half-edited artifact.json fails validation rather than
silently replaying as if nothing changed.
"""
import json

import pytest
from pydantic import ValidationError

from cua.artifact.models import CapabilityArtifact

pytestmark = pytest.mark.unit


def test_fresh_artifact_is_sealed_with_sha256_hex(sample_artifact):
    assert sample_artifact.content_hash is not None
    assert len(sample_artifact.content_hash) == 64
    assert sample_artifact.content_hash == sample_artifact.compute_content_hash()


def test_content_hash_is_stable_across_json_round_trip(sample_artifact):
    dumped = sample_artifact.model_dump_json()
    restored = CapabilityArtifact.model_validate_json(dumped)
    assert restored.content_hash == sample_artifact.content_hash
    assert restored == sample_artifact


def test_omitted_content_hash_on_load_reseals_to_matching_digest(sample_artifact):
    data = sample_artifact.model_dump(mode="json")
    data.pop("content_hash")
    restored = CapabilityArtifact.model_validate(data)
    assert restored.content_hash == sample_artifact.compute_content_hash()


def test_tampered_payload_with_stale_hash_is_rejected(sample_artifact):
    data = sample_artifact.model_dump(mode="json")
    data["description"] = data["description"] + " (edited without resealing)"
    with pytest.raises(ValidationError, match="content_hash does not match"):
        CapabilityArtifact.model_validate(data)


def test_wrong_explicit_hash_is_rejected(sample_artifact):
    data = sample_artifact.model_dump(mode="json")
    data["content_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="content_hash does not match"):
        CapabilityArtifact.model_validate(data)


def test_malformed_content_hash_shape_is_rejected(sample_artifact):
    data = sample_artifact.model_dump(mode="json")
    data["content_hash"] = "not-a-digest"
    with pytest.raises(ValidationError):
        CapabilityArtifact.model_validate(data)


def test_canonical_hash_ignores_pretty_print_whitespace(sample_artifact):
    compact = sample_artifact.model_dump(mode="json")
    pretty = json.dumps(compact, indent=2, sort_keys=False)
    restored = CapabilityArtifact.model_validate_json(pretty)
    assert restored.content_hash == sample_artifact.content_hash


def test_editing_then_clearing_hash_reseals(sample_artifact):
    """In-memory edits that will be re-validated must clear content_hash
    so the seal is recomputed for the new payload."""
    edited = sample_artifact.model_copy(
        update={"description": "Revised description after human review.", "content_hash": None}
    )
    resealed = CapabilityArtifact.model_validate(edited.model_dump(mode="json"))
    assert resealed.description.startswith("Revised")
    assert resealed.content_hash == resealed.compute_content_hash()
    assert resealed.content_hash != sample_artifact.content_hash
