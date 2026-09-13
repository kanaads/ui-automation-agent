import pytest
from pydantic import ValidationError

from cua.artifact.models import OutputSpec, ParamType

pytestmark = pytest.mark.unit


def test_minimal_valid_output_defaults():
    o = OutputSpec(name="member_name", type=ParamType.STRING)
    assert o.sensitive is False
    assert o.nullable is False


def test_sensitive_output_is_allowed_and_flagged():
    o = OutputSpec(name="savings_balance", type=ParamType.NUMBER, sensitive=True)
    assert o.sensitive is True


@pytest.mark.parametrize("bad_name", ["Savings Balance", "savings-balance", "1x"])
def test_name_must_be_a_snake_case_identifier(bad_name):
    with pytest.raises(ValidationError):
        OutputSpec(name=bad_name, type=ParamType.STRING)


def test_nullable_output_is_valid():
    o = OutputSpec(name="middle_name", type=ParamType.STRING, nullable=True)
    assert o.nullable is True
