"""`python -m cua.agent.cli discover` -- the one-shot CLI the assignment's
`make evidence-run` deliverable actually runs: a real LLM-driven
discovery against a real, already-running target app, saved as
evidence (`cua.evidence.save_discovery_evidence`), with a
`CapabilityArtifact` recorded (`cua.agent.recorder`) if the goal was
reached.

Split deliberately into three layers, the same shape every other real
boundary in this project takes:

- `parse_args` -- pure argparse, no I/O, fully unit-tested on its own.
- `execute(args, *, surface, llm, provider, model)` -- the actual
  orchestration (discover -> save evidence -> record an artifact on
  success), taking an already-built `Surface`/`LLMClient` as plain
  parameters. This is the layer real unit tests exercise, against the
  exact same fakes `cua.agent.discover`'s own tests use -- no browser,
  no real LLM, ever, at this tier.
- `main` -- the only place that builds REAL collaborators (a Playwright
  browser navigated to `--target`, an LLM client from
  `build_llm_client_from_env()`) and hands them to `execute`. Not unit
  tested for exactly that reason; proven by the live evidence run
  itself and by `tests/integration/agent`, which already exercises the
  same real-`WebSurface`-plus-fake-LLM combination this module wires
  together for real use.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cua.agent.discover import DEFAULT_MAX_STEPS, discover
from cua.agent.llm.base import LLMClient
from cua.agent.llm.factory import build_llm_client_from_env
from cua.agent.recorder import build_artifact_from_discovery
from cua.artifact.models import (
    Checkpoint,
    LocatorStrategy,
    LocatorTier,
    OutputSpec,
    ParamType,
    TenantScope,
)
from cua.evidence import save_discovery_evidence
from cua.surface.base import Surface
from cua.surface.web import WebSurface


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m cua.agent.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Run one LLM-driven discovery against a live target app.")
    discover_parser.add_argument("--goal", required=True, help="The natural-language goal to hand the model.")
    discover_parser.add_argument("--target", required=True, help="Base URL of the already-running target app.")
    discover_parser.add_argument("--out", required=True, help="Directory to write evidence (and the artifact) into.")
    discover_parser.add_argument("--start-path", default="/app", help="Path appended to --target before discovery starts.")
    discover_parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    discover_parser.add_argument("--capability-id", required=True)
    discover_parser.add_argument("--version", default="1.0.0")
    discover_parser.add_argument("--description", required=True)
    discover_parser.add_argument("--vendor-app-id", default="meridian_core")
    discover_parser.add_argument("--checkpoint-role", required=True, help="Accessible role of the element that proves success.")
    discover_parser.add_argument("--checkpoint-name", required=True, help="Accessible name of the element that proves success.")
    discover_parser.add_argument("--checkpoint-description", default="")
    discover_parser.add_argument(
        "--parameterize",
        action="append",
        default=[],
        metavar="LITERAL=PARAM_NAME",
        help="Repeatable. Turns a literal value the model typed/selected into a named input parameter.",
    )
    discover_parser.add_argument(
        "--output-field",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Repeatable. Declares one output_field name the model may name in an 'extract' "
            "decision -- required for every such name, since CapabilityArtifact rejects a step "
            "that references an undeclared one."
        ),
    )

    return parser.parse_args(argv)


def _parse_parameterize(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        literal, _, param_name = item.partition("=")
        parsed[literal] = param_name
    return parsed


def execute(args: argparse.Namespace, *, surface: Surface, llm: LLMClient, provider: str, model: str) -> int:
    result = discover(args.goal, surface, llm, max_steps=args.max_steps)

    out_dir = Path(args.out)
    save_discovery_evidence(
        out_dir,
        goal=args.goal,
        result=result,
        provider=provider,
        model=model,
        screenshot=surface.screenshot(),
    )

    if not result.succeeded:
        print(f"{result.status.value}: {result.reason}", file=sys.stderr)
        return 1

    artifact = build_artifact_from_discovery(
        result,
        capability_id=args.capability_id,
        version=args.version,
        description=args.description,
        tenant_scope=TenantScope(vendor_app_id=args.vendor_app_id),
        checkpoint=Checkpoint(
            description=args.checkpoint_description,
            detection=LocatorTier(
                strategy=LocatorStrategy.ROLE_NAME, params={"role": args.checkpoint_role, "name": args.checkpoint_name}
            ),
        ),
        parameterize=_parse_parameterize(args.parameterize),
        output_schema=[OutputSpec(name=name, type=ParamType.STRING) for name in args.output_field],
    )
    (out_dir / "artifact.json").write_text(artifact.model_dump_json(indent=2))
    print(f"GOAL_REACHED -> {out_dir / 'artifact.json'}")
    return 0


def build_args(**kwargs: object) -> argparse.Namespace:
    """Constructs the same `Namespace` shape `parse_args` would, without
    going through argv parsing -- what unit tests of `execute` build
    directly rather than round-tripping through CLI strings."""
    return argparse.Namespace(**kwargs)


def main(
    argv: list[str] | None = None,
    *,
    llm_factory: Callable[[Surface], LLMClient] | None = None,
    playwright_driver: Any | None = None,
) -> int:
    """`llm_factory`, when given, replaces `build_llm_client_from_env()`
    -- the one seam this otherwise-real entry point offers, and exactly
    what lets `tests/integration/agent` exercise this exact function
    (real Playwright browser, real target app, real argv parsing) with
    a fixture-driven scripted LLM instead of real credentials, matching
    every other integration test's own "LLM calls are fixture-driven,
    never live" rule. It takes the already-built `Surface` (a scripted
    LLM stand-in typically needs to `observe()` it itself, the same way
    `tests/integration/agent/conftest.py`'s own stand-ins do) rather
    than a ready `LLMClient`, since the real client doesn't exist until
    the browser does. Ordinary CLI use never passes it.

    `playwright_driver`, when given, replaces this function's own
    `sync_playwright()` call with an already-active driver instance --
    Playwright's sync API allows only ONE such driver connection per
    process (see `tests/integration/conftest.py`'s `playwright_instance`
    fixture for the confirmed root cause), so a test suite that already
    holds one open for other fixtures must hand it to `main` rather
    than let this function open a second, conflicting one. Ordinary
    CLI use never passes it either -- a real invocation is the only
    Playwright driver in its process.
    """
    args = parse_args(argv if argv is not None else sys.argv[1:])

    import os

    def _run(p: Any) -> int:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{args.target}{args.start_path}")
            surface = WebSurface(page)
            llm = llm_factory(surface) if llm_factory is not None else build_llm_client_from_env()
            return execute(
                args,
                surface=surface,
                llm=llm,
                provider=os.environ.get("LLM_PROVIDER", "unknown") if llm_factory is None else "fixture",
                model=type(llm).__name__,
            )
        finally:
            browser.close()

    if playwright_driver is not None:
        return _run(playwright_driver)

    # Real CLI use only: a genuine standalone process never has another
    # Playwright driver already open to conflict with, so this is the
    # one branch that can't be exercised inside this project's own test
    # session (see the docstring above) -- proven instead by the actual
    # live evidence run.
    from playwright.sync_api import sync_playwright  # pragma: no cover

    with sync_playwright() as p:  # pragma: no cover
        return _run(p)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
