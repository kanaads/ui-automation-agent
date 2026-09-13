import pytest
from pydantic import ValidationError

from cua.artifact.models import ActionType, LocatorStrategy, LocatorTier, RiskLevel, Step, Target

pytestmark = pytest.mark.unit


def make_target() -> Target:
    return Target(primary=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "button", "name": "Search"}))


def test_navigate_step_does_not_require_a_target():
    s = Step(step_id="s1", action=ActionType.NAVIGATE, literal_value="/members/search")
    assert s.target is None


def test_navigate_step_requires_a_destination():
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.NAVIGATE)


def test_navigate_step_must_not_declare_a_target():
    """Navigate acts on the surface as a whole (a URL/route), not on one
    control, so it should never carry a Target -- carrying one would be a
    sign the step was mis-authored as the wrong action type."""
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.NAVIGATE, literal_value="/members/search", target=make_target())


def test_click_step_requires_a_target():
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.CLICK)


def test_click_step_valid():
    s = Step(step_id="s1", action=ActionType.CLICK, target=make_target())
    assert s.target is not None


def test_type_step_requires_target_and_a_value_source():
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.TYPE, target=make_target())


def test_type_step_valid_with_input_param():
    s = Step(step_id="s1", action=ActionType.TYPE, target=make_target(), input_param="member_id")
    assert s.input_param == "member_id"


def test_type_step_cannot_bind_both_input_param_and_literal_value():
    """A step should have exactly one, unambiguous value source."""
    with pytest.raises(ValidationError):
        Step(
            step_id="s1",
            action=ActionType.TYPE,
            target=make_target(),
            input_param="member_id",
            literal_value="12345",
        )


def test_extract_step_requires_target_and_output_field():
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.EXTRACT, target=make_target())


def test_extract_step_valid():
    s = Step(step_id="s1", action=ActionType.EXTRACT, target=make_target(), output_field="savings_balance")
    assert s.output_field == "savings_balance"


def test_step_id_must_be_a_slug():
    with pytest.raises(ValidationError):
        Step(step_id="Step One!", action=ActionType.NAVIGATE, literal_value="/x")


def test_risky_irreversible_step_requires_a_rationale():
    with pytest.raises(ValidationError):
        Step(
            step_id="s1",
            action=ActionType.CLICK,
            target=make_target(),
            risk=RiskLevel.RISKY_IRREVERSIBLE,
        )


def test_risky_irreversible_step_valid_with_rationale():
    s = Step(
        step_id="s1",
        action=ActionType.CLICK,
        target=make_target(),
        risk=RiskLevel.RISKY_IRREVERSIBLE,
        risk_rationale="Submits an irreversible sub-account opening; requires human confirmation.",
    )
    assert s.risk is RiskLevel.RISKY_IRREVERSIBLE


@pytest.mark.parametrize(
    "value",
    ["123-45-6789", "4111 1111 1111 1111", "4111111111111111"],
)
def test_literal_value_rejects_pii_shaped_strings(value):
    """Never persist raw sensitive data into the artifact (assignment 3.4).
    A recorder that accidentally records a literal SSN/PAN instead of
    parameterizing it must fail loudly at schema-construction time."""
    with pytest.raises(ValidationError):
        Step(step_id="s1", action=ActionType.TYPE, target=make_target(), literal_value=value)


def test_default_timeout_and_retries():
    s = Step(step_id="s1", action=ActionType.CLICK, target=make_target())
    assert s.timeout_ms == 5000
    assert s.max_retries == 0
