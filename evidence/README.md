# Evidence

Populated in Phase 9 with a genuine LLM-driven discovery run and a
deterministic replay run (including one error/exceptional-state replay),
per the assignment's Section 6 deliverable. See README.md's "Evidence
run (CLI)" section for the exact commands.

- `discovery_lookup_balance/` -- one real discovery against AWS Bedrock
  (`us.anthropic.claude-haiku-4-5-20251001-v1:0`): goal "look up member
  10001 and open their detail page", `run.json` + `transcript.json` +
  `final_screenshot.png` + the recorded `artifact.json`.
- `replay_lookup_balance/` -- that artifact replayed deterministically
  (no LLM) for member 10002, a member the discovery run never saw.
  `status: success`.
- `replay_lookup_balance_not_found/` -- the same artifact replayed for
  a member id that doesn't exist. `status: unrecognized` -- correct,
  not a bug: a freshly-discovered artifact has no `known_outcomes` yet,
  so this is `cua.replay`'s error taxonomy correctly refusing to guess
  at a screen no human has annotated, rather than reporting a false
  success (REPORT.md Section 1/7).
