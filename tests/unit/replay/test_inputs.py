"""validate_inputs() is the replay engine's front door: a malformed
invocation (missing/extra/mistyped input, or a step that needs a value
nobody can supply) is a caller bug and must raise before any Surface is
touched -- never degrade into a stuck-looking ReplayResult."""
import pytest

from cua.artifact.models import ActionType, ParamSpec, ParamType, Step, Target
from cua.replay.inputs import ReplayInputError, validate_inputs
from tests.unit.replay.conftest import build_member_balance_artifact, role_tier, type_step_using

pytestmark = pytest.mark.unit


def test_valid_inputs_pass_through_unchanged():
    artifact = build_member_balance_artifact()
    resolved = validate_inputs(artifact, {"member_id": "10001"})
    assert resolved == {"member_id": "10001"}


def test_missing_required_input_raises():
    artifact = build_member_balance_artifact()
    with pytest.raises(ReplayInputError, match="member_id"):
        validate_inputs(artifact, {})


def test_unknown_input_raises():
    artifact = build_member_balance_artifact()
    with pytest.raises(ReplayInputError, match="extra_thing"):
        validate_inputs(artifact, {"member_id": "10001", "extra_thing": "oops"})


def test_optional_input_uses_default_when_omitted():
    artifact = build_member_balance_artifact(
        extra_params=[ParamSpec(name="notes", type=ParamType.STRING, required=False, default="none")],
        extra_steps=[type_step_using("notes")],
    )
    resolved = validate_inputs(artifact, {"member_id": "10001"})
    assert resolved["notes"] == "none"


@pytest.mark.parametrize(
    ("type_", "good", "bad"),
    [
        (ParamType.STRING, "hello", 5),
        (ParamType.INTEGER, 5, "5"),
        (ParamType.INTEGER, 5, 5.5),
        (ParamType.NUMBER, 5.5, "5.5"),
        (ParamType.BOOLEAN, True, "true"),
    ],
)
def test_type_mismatch_raises(type_, good, bad):
    artifact = build_member_balance_artifact(
        extra_params=[ParamSpec(name="extra", type=type_, required=False)],
        extra_steps=[type_step_using("extra")],
    )
    validate_inputs(artifact, {"member_id": "10001", "extra": good})  # sanity: good value is fine
    with pytest.raises(ReplayInputError, match="extra"):
        validate_inputs(artifact, {"member_id": "10001", "extra": bad})


def test_string_pattern_mismatch_raises():
    artifact = build_member_balance_artifact(
        extra_params=[ParamSpec(name="acct_type", type=ParamType.STRING, required=False, pattern=r"^[A-Z]+$")],
        extra_steps=[type_step_using("acct_type")],
    )
    validate_inputs(artifact, {"member_id": "10001", "acct_type": "SAVINGS"})
    with pytest.raises(ReplayInputError, match="acct_type"):
        validate_inputs(artifact, {"member_id": "10001", "acct_type": "savings"})


def test_enum_value_not_in_choices_raises():
    artifact = build_member_balance_artifact(
        extra_params=[
            ParamSpec(name="acct_type", type=ParamType.ENUM, required=False, enum_values=["SAVINGS", "CHECKING"])
        ],
        extra_steps=[type_step_using("acct_type")],
    )
    validate_inputs(artifact, {"member_id": "10001", "acct_type": "SAVINGS"})
    with pytest.raises(ReplayInputError, match="acct_type"):
        validate_inputs(artifact, {"member_id": "10001", "acct_type": "MONEY_MARKET"})


def test_step_referencing_an_unsuppliable_optional_input_raises():
    """A step whose input_param is optional and has no default can pass
    schema construction (Phase 1 only checks the param is *declared*),
    but is a broken artifact at replay time if the caller doesn't happen
    to supply it -- catch that here, before touching a Surface, rather
    than failing confusingly mid-flow."""
    artifact = build_member_balance_artifact(
        extra_params=[ParamSpec(name="notes", type=ParamType.STRING, required=False)],
        extra_steps=[
            Step(
                step_id="type_notes",
                action=ActionType.TYPE,
                target=Target(primary=role_tier("textbox", "Notes")),
                input_param="notes",
            )
        ],
    )
    with pytest.raises(ReplayInputError, match="notes"):
        validate_inputs(artifact, {"member_id": "10001"})
