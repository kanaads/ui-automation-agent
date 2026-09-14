"""`python -m cua.replay.cli run` -- the deterministic half of the
assignment's evidence deliverable: replays a saved `CapabilityArtifact`
(no LLM involved) against a live target app and saves the result as
evidence. Same three-layer split as `cua.agent.cli`:

- `parse_args` -- pure argparse.
- `execute(args, *, artifact, surface)` -- the real orchestration
  (`cua.policy.guarded_replay` -> `cua.evidence.save_replay_evidence`),
  taking an already-loaded `CapabilityArtifact` and an already-built
  `Surface` as plain parameters -- unit-tested against the exact same
  `ScriptedSurface`/`build_member_balance_artifact()` fixtures
  `cua.replay.engine`'s own tests use.
- `main` -- reads `--artifact` off disk and wires a real Playwright
  browser; not unit tested for the same reason `cua.agent.cli.main`
  isn't -- proven for real by `tests/integration/replay` and
  `tests/integration/policy` already exercising this exact
  `guarded_replay` call against the real app, and by the live evidence
  run itself.

Always goes through `cua.policy.guarded_replay`, never
`cua.replay.replay` directly -- the same "the safety-gated path is the
default, not an opt-in" choice README.md's own demo snippet recommends
(REPORT.md Section 6). `--authorize` is how a human running this CLI
supplies the same per-invocation authorization
`authorized_step_ids` already requires everywhere else in this
project -- there is no flag that authorizes every risky step at once.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cua.artifact.models import CapabilityArtifact
from cua.evidence import save_replay_evidence
from cua.policy import guarded_replay
from cua.surface.base import Surface
from cua.surface.web import WebSurface


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m cua.replay.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Deterministically replay a saved artifact against a live target app.")
    run_parser.add_argument("--artifact", required=True, help="Path to a saved artifact.json.")
    run_parser.add_argument("--target", required=True, help="Base URL of the already-running target app.")
    run_parser.add_argument("--out", required=True, help="Directory to write evidence into.")
    run_parser.add_argument(
        "--start-path", default="/nav", help="Path appended to --target before replay begins (must give the frame a real base URL)."
    )
    run_parser.add_argument(
        "--param", action="append", default=[], metavar="NAME=VALUE", help="Repeatable. One artifact input parameter."
    )
    run_parser.add_argument(
        "--authorize",
        action="append",
        default=[],
        metavar="STEP_ID",
        help="Repeatable. Authorizes one RISKY_IRREVERSIBLE step id for this invocation only.",
    )

    return parser.parse_args(argv)


def _parse_params(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        name, _, value = item.partition("=")
        parsed[name] = value
    return parsed


def execute(args: argparse.Namespace, *, artifact: CapabilityArtifact, surface: Surface) -> int:
    raw_inputs = _parse_params(args.param)
    result = guarded_replay(artifact, raw_inputs, surface, authorized_step_ids=frozenset(args.authorize))

    out_dir = Path(args.out)
    save_replay_evidence(out_dir, artifact=artifact, raw_inputs=raw_inputs, result=result, screenshot=surface.screenshot())

    if result.needs_escalation:
        print(f"{result.status.value}: {result.reason}", file=sys.stderr)
        return 1

    print(f"{result.status.value} -> {out_dir / 'result.json'}")
    return 0


def build_args(**kwargs: object) -> argparse.Namespace:
    """Constructs the same `Namespace` shape `parse_args` would, without
    going through argv parsing -- what unit tests of `execute` build
    directly rather than round-tripping through CLI strings."""
    return argparse.Namespace(**kwargs)


def main(argv: list[str] | None = None, *, playwright_driver: Any | None = None) -> int:
    """`playwright_driver`, when given, replaces this function's own
    `sync_playwright()` call with an already-active driver instance --
    Playwright's sync API allows only ONE such driver connection per
    process (see `tests/integration/conftest.py`'s `playwright_instance`
    fixture for the confirmed root cause), so a test suite that already
    holds one open for other fixtures must hand it to `main` rather
    than let this function open a second, conflicting one. Ordinary
    CLI use never passes it -- a real invocation is the only Playwright
    driver in its process.
    """
    args = parse_args(argv if argv is not None else sys.argv[1:])
    artifact = CapabilityArtifact.model_validate_json(Path(args.artifact).read_text())

    def _run(p: Any) -> int:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{args.target}{args.start_path}")
            surface = WebSurface(page)
            return execute(args, artifact=artifact, surface=surface)
        finally:
            browser.close()

    if playwright_driver is not None:
        return _run(playwright_driver)

    # Real CLI use only -- see the docstring above and
    # cua.agent.cli.main's identical branch for why this can't be
    # exercised inside this project's own test session.
    from playwright.sync_api import sync_playwright  # pragma: no cover

    with sync_playwright() as p:  # pragma: no cover
        return _run(p)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
