"""cua.agent.cli.execute: the CLI's actual orchestration (discover ->
save evidence -> record an artifact on success), fully decoupled from
argument parsing and from how `surface`/`llm` were built -- both are
plain parameters here, so this is tested against the exact same
ScriptedSurface/FakeLLMClient fakes `cua.agent.discover`'s own unit
tests already use, no browser and no real LLM anywhere. `main()`
(untested at this tier) is the only place that wires a real
Playwright browser and `build_llm_client_from_env()` together --
proven for real in tests/integration/agent and the live evidence run
itself.
"""
import json

import pytest

from cua.agent.cli import build_args, execute
from tests.unit.agent.conftest import FakeLLMClient
from tests.unit.replay.conftest import ScriptedSurface, node

pytestmark = pytest.mark.unit


def _decision(action: str, **kwargs) -> str:
    return json.dumps({"thought": "t", "action": action, **kwargs})


def _search_screen():
    from cua.surface.models import Observation

    return Observation(
        nodes=[node("e10", "contentFrame", "textbox", None), node("e13", "contentFrame", "button", "Search")],
        url="http://x/content/search",
        title="Member Search",
    )


def _detail_screen():
    from cua.surface.models import Observation

    return Observation(
        nodes=[
            node("d2", "contentFrame", "heading", "Member Detail"),
            node("d3", "contentFrame", "cell", "Savings Balance", parent_ref=None),
            node("d4", "contentFrame", "cell", "$4,231.50", parent_ref=None),
        ],
        url="http://x/content/detail",
        title="Member Detail",
    )


def _args(tmp_path, **overrides):
    defaults = {
        "goal": "look up member 10001",
        "target": "http://x",
        "out": str(tmp_path / "out"),
        "capability_id": "look_up_member",
        "version": "1.0.0",
        "description": "Look up a member.",
        "vendor_app_id": "meridian_core",
        "checkpoint_role": "heading",
        "checkpoint_name": "Member Detail",
        "checkpoint_description": "",
        "parameterize": [],
        "output_field": [],
        "max_steps": 15,
        "start_path": "/app",
    }
    defaults.update(overrides)
    return build_args(**defaults)


def test_execute_on_goal_reached_saves_evidence_and_writes_an_artifact(tmp_path):
    llm = FakeLLMClient([_decision("click", frame="contentFrame", ref="e13"), _decision("done")])
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "e13", advance=True)

    exit_code = execute(_args(tmp_path), surface=surface, llm=llm, provider="bedrock", model="my-model")

    assert exit_code == 0
    out = tmp_path / "out"
    assert (out / "run.json").exists()
    assert (out / "transcript.json").exists()
    artifact = json.loads((out / "artifact.json").read_text())
    assert artifact["capability_id"] == "look_up_member"
    assert artifact["checkpoint"]["detection"]["params"] == {"role": "heading", "name": "Member Detail"}


def test_execute_parameterizes_a_typed_literal_into_the_declared_input(tmp_path):
    llm = FakeLLMClient(
        [_decision("type", frame="contentFrame", ref="e10", value="10001"), _decision("click", frame="contentFrame", ref="e13"), _decision("done")]
    )
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "e10", advance=False)
    surface.script("contentFrame", "e13", advance=True)

    exit_code = execute(
        _args(tmp_path, parameterize=["10001=member_id"]), surface=surface, llm=llm, provider="bedrock", model="m"
    )

    assert exit_code == 0
    artifact = json.loads((tmp_path / "out" / "artifact.json").read_text())
    type_step = next(s for s in artifact["steps"] if s["action"] == "type")
    assert type_step["input_param"] == "member_id"
    assert type_step["literal_value"] is None
    assert {p["name"] for p in artifact["input_schema"]} == {"member_id"}


@pytest.mark.parametrize("second_decision", [_decision("stuck", reason="no way to proceed")])
def test_execute_on_stuck_saves_evidence_but_writes_no_artifact_and_returns_nonzero(tmp_path, second_decision):
    llm = FakeLLMClient([second_decision])
    surface = ScriptedSurface([_search_screen()])

    exit_code = execute(_args(tmp_path), surface=surface, llm=llm, provider="bedrock", model="m")

    assert exit_code == 1
    out = tmp_path / "out"
    assert (out / "run.json").exists()
    assert not (out / "artifact.json").exists()


def test_execute_declares_output_fields_named_by_a_real_extract_decision(tmp_path):
    """A discovery that ends by extracting a value (the model names the
    output_field on the spot -- it isn't known ahead of time) only
    records an artifact if that name is declared in the schema
    CapabilityArtifact validates against; --output-field is how the
    CLI caller supplies that declaration. This reproduces exactly what
    a real live discovery run hit: build_artifact_from_discovery raised
    "references undeclared output_field 'savings_balance'" until this
    flag existed."""
    llm = FakeLLMClient(
        [
            _decision("click", frame="contentFrame", ref="e13"),
            _decision("extract", frame="contentFrame", ref="d4", output_field="savings_balance"),
            _decision("done"),
        ]
    )
    surface = ScriptedSurface([_search_screen(), _detail_screen()])
    surface.script("contentFrame", "e13", advance=True)

    exit_code = execute(
        _args(tmp_path, output_field=["savings_balance"]), surface=surface, llm=llm, provider="bedrock", model="m"
    )

    assert exit_code == 0
    artifact = json.loads((tmp_path / "out" / "artifact.json").read_text())
    assert {o["name"] for o in artifact["output_schema"]} == {"savings_balance"}
    extract_step = next(s for s in artifact["steps"] if s["action"] == "extract")
    assert extract_step["output_field"] == "savings_balance"


def test_execute_passes_max_steps_through_to_discover(tmp_path):
    llm = FakeLLMClient([_decision("click", frame="contentFrame", ref="e13") for _ in range(5)])
    surface = ScriptedSurface([_search_screen()])  # never advances

    exit_code = execute(_args(tmp_path, max_steps=2), surface=surface, llm=llm, provider="bedrock", model="m")

    assert exit_code == 1
    run = json.loads((tmp_path / "out" / "run.json").read_text())
    assert run["status"] == "max_steps_exceeded"
    assert run["steps_taken"] == 2
