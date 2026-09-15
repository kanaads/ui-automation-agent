# Evidence

Populated in Phase 9 with a genuine LLM-driven discovery run and
deterministic replay runs (happy path, unrecognized exceptional path,
and a declared business-outcome path), per the assignment's Section 6
deliverable. See README.md's "Evidence run (CLI)" section for the exact
commands.

Every checked-in `artifact.json` carries a `content_hash` seal (SHA-256
over the canonical payload excluding the hash field itself); loading a
tampered file fails validation (REPORT.md Section 2).

- `discovery_lookup_balance/` -- one real discovery against AWS Bedrock
  (`us.anthropic.claude-haiku-4-5-20251001-v1:0`): goal "look up member
  10001 and open their detail page", `run.json` + `transcript.json` +
  `final_screenshot.png` + the recorded `artifact.json`.
- `replay_lookup_balance/` -- that artifact replayed deterministically
  (no LLM) for member 10002, a member the discovery run never saw.
  `status: success`.
- `replay_lookup_balance_not_found/` -- the same *fresh* discovery
  artifact replayed for a member id that doesn't exist.
  `status: unrecognized` -- correct, not a bug: a freshly-discovered
  artifact has no `known_outcomes` yet, so this is `cua.replay`'s error
  taxonomy correctly refusing to guess at a screen no human has
  annotated (REPORT.md Section 1/7).
- `replay_lookup_balance_business_outcome/` -- the same flow after a
  human reviewer annotated `known_outcomes` with `MEMBER_NOT_FOUND`
  (hand-authored `artifact.json` in this folder, sealed). Replayed for
  member `99999`. `status: business_outcome`, `outcome_code:
  MEMBER_NOT_FOUND` -- the full declared taxonomy path, not an
  unrecognized guess.
