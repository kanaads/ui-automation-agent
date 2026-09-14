"""cua.agent.cli.main against the real target app: real argv parsing,
a real Playwright browser, a real WebSurface -- only the LLM is
fixture-driven (`llm_factory`, the one seam `main` offers exactly for
this), via the same `LookUpMemberScript` stand-in
tests/integration/agent/test_discover_live.py already proves against
the real search -> detail flow.
"""
import pytest

from cua.agent.cli import main
from tests.integration.agent.conftest import LookUpMemberScript

pytestmark = pytest.mark.integration


def test_main_on_goal_reached_writes_evidence_and_an_artifact(live_app, tmp_path, playwright_instance):
    out_dir = tmp_path / "evidence"

    exit_code = main(
        [
            "discover",
            "--goal", "Look up member 10001 and open their detail page.",
            "--target", live_app,
            "--out", str(out_dir),
            "--capability-id", "look_up_member",
            "--description", "Look up a member by id and open their detail page.",
            "--checkpoint-role", "heading",
            "--checkpoint-name", "Member Detail",
            "--parameterize", "10001=member_id",
        ],
        llm_factory=lambda surface: LookUpMemberScript(surface, member_id="10001"),
        playwright_driver=playwright_instance,
    )

    assert exit_code == 0
    assert (out_dir / "run.json").exists()
    assert (out_dir / "transcript.json").exists()
    assert (out_dir / "final_screenshot.png").exists()
    assert (out_dir / "final_screenshot.png").stat().st_size > 0
    assert (out_dir / "artifact.json").exists()


def test_main_on_max_steps_exceeded_writes_evidence_but_no_artifact_and_exits_nonzero(live_app, tmp_path, playwright_instance):
    out_dir = tmp_path / "evidence"

    class NeverFinishes:
        def complete(self, messages):
            import json

            return json.dumps({"thought": "stuck", "action": "stuck", "reason": "cannot find a way to proceed"})

    exit_code = main(
        [
            "discover",
            "--goal", "Look up member 10001.",
            "--target", live_app,
            "--out", str(out_dir),
            "--capability-id", "look_up_member",
            "--description", "d",
            "--checkpoint-role", "heading",
            "--checkpoint-name", "Member Detail",
        ],
        llm_factory=lambda surface: NeverFinishes(),
        playwright_driver=playwright_instance,
    )

    assert exit_code == 1
    assert (out_dir / "run.json").exists()
    assert not (out_dir / "artifact.json").exists()
