"""cua.replay.cli's argument parsing, in isolation -- see test_execute.py
for the actual orchestration, tested against a fake Surface."""
import pytest

from cua.replay.cli import parse_args

pytestmark = pytest.mark.unit

_REQUIRED = [
    "run",
    "--artifact", "evidence/lookup/artifact.json",
    "--target", "http://localhost:8000",
    "--out", "evidence/replay",
    "--param", "member_id=10001",
]


def test_parses_the_required_flags():
    args = parse_args(_REQUIRED)

    assert args.artifact == "evidence/lookup/artifact.json"
    assert args.target == "http://localhost:8000"
    assert args.out == "evidence/replay"
    assert args.param == ["member_id=10001"]


def test_defaults_start_path_and_authorize():
    args = parse_args(_REQUIRED)

    assert args.start_path == "/nav"
    assert args.authorize == []


def test_parses_repeated_param_and_authorize_flags():
    args = parse_args(
        [*_REQUIRED, "--param", "account_type=SAVINGS", "--authorize", "click_confirm", "--authorize", "click_submit"]
    )

    assert args.param == ["member_id=10001", "account_type=SAVINGS"]
    assert args.authorize == ["click_confirm", "click_submit"]


@pytest.mark.parametrize("missing", ["--artifact", "--target", "--out"])
def test_missing_a_required_flag_raises(missing):
    idx = _REQUIRED.index(missing)
    args = _REQUIRED[:idx] + _REQUIRED[idx + 2 :]

    with pytest.raises(SystemExit):
        parse_args(args)
