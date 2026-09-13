import pytest
from pydantic import ValidationError

from cua.artifact.models import Checkpoint, KnownOutcome, LocatorStrategy, LocatorTier

pytestmark = pytest.mark.unit


def detector() -> LocatorTier:
    return LocatorTier(
        strategy=LocatorStrategy.LABEL_PROXIMITY,
        params={"near_text": "No records match", "control_type": "text"},
    )


def test_checkpoint_requires_description_and_detection():
    with pytest.raises(ValidationError):
        Checkpoint(description="Member detail loaded")


def test_checkpoint_valid():
    c = Checkpoint(description="Member detail loaded", detection=detector())
    assert c.description


@pytest.mark.parametrize("category", ["business_outcome", "recoverable", "hard_failure"])
def test_known_outcome_accepts_declared_categories(category):
    k = KnownOutcome(code="X", description="d", category=category, detection=detector())
    assert k.category == category


def test_known_outcome_rejects_unknown_category():
    with pytest.raises(ValidationError):
        KnownOutcome(code="X", description="d", category="crash", detection=detector())


def test_known_outcome_code_must_be_shouty_snake_case():
    with pytest.raises(ValidationError):
        KnownOutcome(code="memberNotFound", description="d", category="business_outcome", detection=detector())


def test_known_outcome_valid_code():
    k = KnownOutcome(code="MEMBER_NOT_FOUND", description="d", category="business_outcome", detection=detector())
    assert k.code == "MEMBER_NOT_FOUND"
