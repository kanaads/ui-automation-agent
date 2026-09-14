"""cua.replay.cli.main against the real target app: real argv
parsing, a real artifact.json read off disk, a real Playwright
browser. No LLM at all in this half of the pipeline, so unlike
cua.agent.cli.main this needs no fixture-driven seam -- everything
here is exactly what a real invocation of `make replay` runs.
"""
import pytest

from cua.replay.cli import main
from tests.unit.replay.conftest import build_member_balance_artifact

pytestmark = pytest.mark.integration


def test_main_replays_the_real_search_to_detail_flow_and_writes_evidence(live_app, tmp_path, playwright_instance):
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(build_member_balance_artifact().model_dump_json())
    out_dir = tmp_path / "evidence"

    exit_code = main(
        [
            "run",
            "--artifact", str(artifact_path),
            "--target", live_app,
            "--out", str(out_dir),
            "--param", "member_id=10001",
        ],
        playwright_driver=playwright_instance,
    )

    assert exit_code == 0
    assert (out_dir / "result.json").exists()
    assert (out_dir / "final_screenshot.png").exists()
    assert (out_dir / "final_screenshot.png").stat().st_size > 0

    import json

    result = json.loads((out_dir / "result.json").read_text())
    assert result["status"] == "success"
    assert result["outputs"]["balance_text"] == "$4,231.50"


def test_main_on_a_nonexistent_member_reaches_the_declared_business_outcome(live_app, tmp_path, playwright_instance):
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(build_member_balance_artifact().model_dump_json())
    out_dir = tmp_path / "evidence"

    exit_code = main(
        ["run", "--artifact", str(artifact_path), "--target", live_app, "--out", str(out_dir), "--param", "member_id=99999"],
        playwright_driver=playwright_instance,
    )

    assert exit_code == 0
    import json

    result = json.loads((out_dir / "result.json").read_text())
    assert result["status"] == "business_outcome"
    assert result["outcome_code"] == "MEMBER_NOT_FOUND"
