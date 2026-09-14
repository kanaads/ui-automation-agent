"""cua.agent.cli's argument parsing, in isolation from everything that
actually touches a browser or an LLM (that's execute(), tested
separately against fakes -- see test_execute.py)."""
import pytest

from cua.agent.cli import parse_args

pytestmark = pytest.mark.unit

_REQUIRED = [
    "discover",
    "--goal", "look up member 10001",
    "--target", "http://localhost:8000",
    "--out", "evidence/lookup",
    "--capability-id", "look_up_member",
    "--description", "Look up a member and read their balance.",
    "--checkpoint-role", "heading",
    "--checkpoint-name", "Member Detail",
]


def test_parses_the_required_flags():
    args = parse_args(_REQUIRED)

    assert args.goal == "look up member 10001"
    assert args.target == "http://localhost:8000"
    assert args.out == "evidence/lookup"
    assert args.capability_id == "look_up_member"
    assert args.checkpoint_role == "heading"
    assert args.checkpoint_name == "Member Detail"


def test_defaults_version_and_start_path_and_max_steps():
    args = parse_args(_REQUIRED)

    assert args.version == "1.0.0"
    assert args.start_path == "/app"
    assert args.max_steps == 15
    assert args.vendor_app_id == "meridian_core"
    assert args.parameterize == []
    assert args.output_field == []


def test_parses_repeated_parameterize_flags():
    args = parse_args([*_REQUIRED, "--parameterize", "10001=member_id", "--parameterize", "SAVINGS=account_type"])

    assert args.parameterize == ["10001=member_id", "SAVINGS=account_type"]


def test_parses_repeated_output_field_flags():
    """A discovery that ends in an `extract` step names an output_field
    the model chose on the spot (e.g. "savings_balance") -- the
    resulting artifact's own schema must declare that same name or
    CapabilityArtifact validation rejects it, and only the CLI caller
    can supply this ahead of time (a real discovery run surfaced this:
    build_artifact_from_discovery raised "references undeclared
    output_field" until this flag existed)."""
    args = parse_args([*_REQUIRED, "--output-field", "savings_balance", "--output-field", "member_status"])

    assert args.output_field == ["savings_balance", "member_status"]


@pytest.mark.parametrize(
    "missing", ["--goal", "--target", "--out", "--capability-id", "--description", "--checkpoint-role", "--checkpoint-name"]
)
def test_missing_a_required_flag_raises(missing):
    args = [a for a in _REQUIRED if a != missing]
    # drop the flag's value too
    idx = _REQUIRED.index(missing)
    args = _REQUIRED[:idx] + _REQUIRED[idx + 2 :]

    with pytest.raises(SystemExit):
        parse_args(args)
