import pytest
from pydantic import ValidationError

from cua.artifact.models import ParamSpec, ParamType

pytestmark = pytest.mark.unit


def test_minimal_valid_param_defaults():
    p = ParamSpec(name="member_id", type=ParamType.STRING)
    assert p.required is True
    assert p.sensitive is False
    assert p.default is None


def test_pattern_is_rejected_on_non_string_types():
    with pytest.raises(ValidationError):
        ParamSpec(name="amount", type=ParamType.NUMBER, pattern=r"^\d+$")


def test_enum_type_requires_enum_values():
    with pytest.raises(ValidationError):
        ParamSpec(name="status", type=ParamType.ENUM)


def test_enum_type_with_values_is_valid():
    p = ParamSpec(name="status", type=ParamType.ENUM, enum_values=["ACTIVE", "CLOSED"])
    assert p.enum_values == ["ACTIVE", "CLOSED"]


def test_enum_values_rejected_on_non_enum_type():
    with pytest.raises(ValidationError):
        ParamSpec(name="status", type=ParamType.STRING, enum_values=["ACTIVE"])


@pytest.mark.parametrize("bad_name", ["Member ID", "member-id", "1id", "id!", ""])
def test_name_must_be_a_snake_case_identifier(bad_name):
    with pytest.raises(ValidationError):
        ParamSpec(name=bad_name, type=ParamType.STRING)


def test_sensitive_param_cannot_declare_a_default_value():
    """A default is an example value baked into the contract; for a field
    marked sensitive that would mean shipping example PII/secrets inside
    the artifact itself, which the schema must not allow."""
    with pytest.raises(ValidationError):
        ParamSpec(name="ssn", type=ParamType.STRING, sensitive=True, default="123-45-6789")


def test_non_sensitive_param_may_declare_a_default_value():
    p = ParamSpec(name="channel", type=ParamType.STRING, default="phone", required=False)
    assert p.default == "phone"
