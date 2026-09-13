# Design write-up

> Status: in progress, filled in as each phase lands. Headings are fixed
> per the assignment brief; content will be completed in the final phase.

## 1. Architecture

*(pending overall narrative; the proxy target is built)*

**Proxy target.** Rather than a public demo/sandbox site, the target is a
self-built "hostile legacy" credit-union back office (`cua.target_app`,
~85 tests, 100% coverage): nested named iframes (`navFrame`/`contentFrame`)
standing in for a classic frameset (real `<frameset>` renders unreliably in
headless Chromium; two iframes pose the identical "which frame is this
control in" problem while staying fully automatable), table-based layout,
no `id`/`data-testid`/`<label for>` anywhere. Two flows: member search →
detail (read-only balance lookup) and open-sub-account → confirm → commit
(multi-field form with a confirmation checkpoint ahead of the one
RISKY_IRREVERSIBLE action). A `FaultController` lets any test or the
evidence-run script arm a specific runtime condition -- session timeout,
permission denial, slow load, a surprise interstitial, a forced validation
error -- on a specific route for a specific browser session, so the
"replay must accommodate real runtime errors" requirement is demonstrable
on demand rather than a matter of luck. Two tenant variants (`base`,
`tenant_b`) share identical structure/field names but differ in branding
and one control's accessible name (the search button), as a deliberately
small stand-in for "hundreds of tenants on the same vendor product."
Trade-off: building the target cost roughly half a day, but it's the only
way to produce on-demand evidence for every branch of the error taxonomy
(Section 3) and to exercise a locator strategy that would be trivial
against a clean modern DOM.

**Surface abstraction** (`cua.surface`, ~50 tests, 100% coverage). A
`Surface` has exactly four methods -- `observe() -> Observation`,
`act(SurfaceAction) -> ActionResult`, `screenshot()`, `current_url()` --
and deliberately no `open()`/`close()`: the live session must survive a
human-escalation handoff (3.6), so lifecycle belongs to whatever creates
a Surface, never to the Surface itself. `WebSurface` perceives via
Playwright's `Locator.aria_snapshot(mode="ai")` on every frame (the main
page plus every named iframe) rather than the older CDP accessibility
API, which the pinned Playwright version no longer exposes; `mode="ai"`
specifically hands back a stable per-frame `ref` that a same-process
`locator("aria-ref=...")` call resolves to a live element later. Acting
is always against a `(frame, ref)` pair from a prior `observe()` --
never a raw coordinate -- and `act()` never raises for an expected
failure (missing element, timeout); it returns a structured
`ActionResult(ok=False, error=...)`, pushing the business/recoverable/
hard-failure classification to the replay layer above it, where the
result contract actually lives. `DesktopSurface` is a real subclass of
`Surface` that raises `NotImplementedError` from every method -- a
design seam, not a demo: a real build would map Windows UIA / macOS AX /
the Java Access Bridge onto the exact same `ObservedNode(role, name,
...)` shape `WebSurface` produces from ARIA, since an accessibility tree
is an OS-level concept, not a web one. Confirmed live against the target
app: the search field genuinely has no accessible name (`textbox` with
`name=None`), forcing real reliance on nearby-text resolution once the
locator layer (next phase) is built, rather than a locator strategy that
only looks robust because the target never actually tested it.

**Locator ladder** (`cua.locator`, ~22 tests, 100% coverage).
`resolve_target(observation, target)` walks a `Target`'s `primary`
locator then its ordered `fallbacks`, matching each tier's strategy
against the live `Observation` until exactly one candidate comes back,
and returns a structured `Resolution(status, frame, ref, tier_index,
strategy, candidates)` -- `RESOLVED` / `AMBIGUOUS` / `NOT_FOUND`, never a
best guess. `ROLE_NAME` is a straight (role, name) match across every
frame; it is the tier that genuinely fails on the target app's search
box, proven live (Section 1), which is what forces `LABEL_PROXIMITY` to
matter rather than being decorative. `LABEL_PROXIMITY` finds node(s)
whose accessible name contains the given text, then searches the
*subtree rooted at that label's parent* for a descendant of the given
role -- matching the real shape a table-based legacy form produces
(label cell and control cell as row siblings), not an idealized
label-next-to-input DOM. `ANCHORED_REGION` is the purely positional
fallback: the `index`-th node whose own role equals `region`, in
document order, within a named frame -- deliberately the target's own
role rather than a container to descend into, so the tier resolves
straight to an actionable leaf (provable by actually clicking the
resolved ref, not just asserting a status) instead of a row/cell
wrapper. `VISUAL_TEMPLATE` is schema-validated but always contributes
zero candidates -- a declared, not silently-dropped, cut (Section 7).
Ambiguity is never resolved by picking the first match:
`Target.ambiguity_policy` either stops at the first tier with more than
one candidate (`escalate_on_ambiguous`, the schema default -- the safe
choice when a wrong click is costly) or keeps trying later tiers for one
that resolves uniquely, only reporting the first ambiguous tier if none
ever do (`first_unique_match`). Proven against a live cross-tenant
scenario, not just synthetic fixtures: the identical artifact `Target`
recorded against the base tenant's "Search" button genuinely returns
`NOT_FOUND` on `tenant_b` (relabeled "Find Member") when only the
`ROLE_NAME` tier is available, and `RESOLVED` -- at a real, clickable ref
-- once an `ANCHORED_REGION` fallback is added, which is the concrete
evidence behind the multi-tenant reuse story in Section 4.

## 2. Artifact schema

The `CapabilityArtifact` schema (`src/cua/artifact/models.py`, ~85 unit
tests, 100% line coverage) is implemented and is the first piece built,
deliberately, since every later layer (replay, policy, escalation) is a
consumer of its shape. Full rationale to follow; the shape itself:

- **Typed contract**: `input_schema` / `output_schema` are lists of typed,
  named, optionally-sensitive parameter specs — the agent-invocable
  function signature.
- **Tiered locators**: each `Target` has a `primary` locator plus an
  ordered `fallbacks` ladder (role+name → label proximity → anchored
  region → a shape-validated but not-yet-executed visual-template tier),
  so "how is this control identified" is a first-class, reviewable part of
  the artifact rather than a single brittle selector.
- **Declared known outcomes**: business outcomes / recoverable conditions
  / hard failures are named on the artifact itself (`known_outcomes`),
  not discovered ad hoc by replay code.
- **Self-declared policy footprint**: `policy_scope.allowed_action_types`
  must cover every action type the recorded steps actually use — checked
  at construction time.
- **Tenant scope seam**: `tenant_scope` distinguishes a base capability
  from a tenant-specific override (with a required back-reference), for
  the multi-tenant reuse story in Section 4.
- **Redaction by construction**: a sensitive `ParamSpec`/`OutputSpec` can
  never carry a baked-in example value; a `Step.literal_value` that looks
  SSN/PAN-shaped is rejected outright; `to_log_safe_dict()` masks captured
  DOM hints for any step that touches a sensitive field before anything
  is written to a log or evidence file.

## 3. Determinism & error handling

The replay engine (`cua.replay`, ~55 tests across unit + live
integration, 100% coverage) is the piece that actually executes a
`CapabilityArtifact` with no LLM in the loop. `validate_inputs()` runs
first and entirely separately from execution: a missing/unknown/mistyped
input, or a step whose `input_param` is optional with no default and
wasn't supplied, raises `ReplayInputError` before any `Surface` is
touched -- a malformed invocation is the caller's bug, not something
that happened in the UI, so it's never allowed to come back looking
like "the system got stuck."

`replay()` then walks `artifact.steps` in order. For every targeted
action it re-observes the surface fresh and checks every declared
`KnownOutcome` *before* attempting to resolve the step's own target --
a declared outcome always wins outright, which is what lets a fault
(session timeout, a surprise dialog, "no such member") short-circuit
the flow at exactly the point it actually occurred rather than
surfacing one step later as a confusing failure. Only once no known
outcome matches does it resolve `step.target` via Phase 4's
`resolve_target`; anything but a clean, unique `RESOLVED` becomes
`UNRECOGNIZED` -- a state nobody declared, never a guess -- and acting
retries up to `step.max_retries` times with a *fresh* observe+resolve
each attempt, since a stale ref from a failed attempt is meaningless to
retry against. Once every step has succeeded, the artifact's own
`checkpoint` is checked against one final fresh observation before
`SUCCESS` is returned: finishing the step list is not itself proof the
goal was reached.

**The result contract** (`ReplayStatus` + `ReplayResult`) makes the
error taxonomy the assignment asks for concrete, reusing
`KnownOutcome.category` directly rather than inventing a parallel one:

- `SUCCESS` / `BUSINESS_OUTCOME` -- both a legitimate, understood ending
  for an invocation (the difference is only whether the happy-path
  checkpoint was reached or a declared alternate ending was); neither
  needs escalation.
- `RECOVERABLE` / `HARD_FAILURE` -- the run stopped short at a declared
  `KnownOutcome`; `needs_escalation` is true for both, but the category
  is preserved so a human (or the escalation layer, Section 5) sees
  *why* without re-reading the transcript.
- `UNRECOGNIZED` -- the engine's own signal: no declared outcome
  explains what happened (target not found or ambiguous, or an action
  genuinely failed after retries, or the checkpoint never confirmed).
  Also always escalates, and is arguably the most urgent case: it means
  the artifact itself may be stale against a changed UI, not just that
  this one run hit bad luck.

Deliberately out of scope for this engine (documented in Section 7, not
silently skipped): it never attempts automatic recovery from a
`recoverable` outcome (dismissing a dialog and resuming) -- only correct
detection and classification. Acting on that belongs to the agent loop
and the escalation layer above it. Likewise `RISKY_IRREVERSIBLE` steps
run exactly like any other step here; gating them is `cua.policy`'s job
(Section 6), not this executor's -- it faithfully does what the
artifact says.

**Proven live, not just against synthetic fixtures**: the exact same
`member_balance_artifact` (search → detail, four declared
`KnownOutcome`s) is replayed both against a fully scripted fake
`Surface` (unit tier) and against a real browser driving a real,
running instance of the target app (integration tier) -- including
genuine fault injection via Phase 2's `FaultController` to force
`SESSION_EXPIRED`, `ACCESS_DENIED`, and a surprise `UNEXPECTED_CONFIRM_DIALOG`
on demand, and a real nonexistent member ID to reach `MEMBER_NOT_FOUND`.

That live proof caught two real, previously-latent bugs neither the
Phase 3/4 fixtures nor synthetic Phase 5 unit tests happened to exercise:

1. **A same-origin iframe's accessible subtree is recursed into by
   Chromium and duplicated.** `WebSurface.observe()` snapshots every
   named frame independently to get correct `frame` labels, but the
   *parent* frame's own snapshot, taken through the shell page rather
   than a bare fragment page, turned out to already contain the child
   frame's entire subtree inline, under the same refs. Every control
   inside an iframe was reporting `AMBIGUOUS` the instant a real page
   had one. Fixed in `cua.surface.aria_parser`: an `iframe` node is
   kept as a landmark leaf, but its recursed-into descendant lines are
   now discarded during parsing -- that content is captured once,
   correctly labeled, when the caller snapshots that frame directly.
2. **A click that triggers navigation only starts one.** `locator.click()`
   doesn't wait for a resulting redirect to finish, and it turned out
   `frame.wait_for_load_state()` called right after isn't a fix either
   -- confirmed live it can return immediately against the frame's
   *pre-click* state, before the browser has even begun navigating. The
   result was a real, intermittent (roughly one-in-five) bug: the very
   next `observe()` racing the redirect and reporting the step right
   after a navigating click as `UNRECOGNIZED`. Fixed in
   `WebSurface._click_and_settle()` using `frame.expect_navigation()`,
   which starts listening *before* the click rather than after, with a
   `clicked` flag to tell "the click itself failed" apart from "the
   click succeeded but didn't need to wait for anything" -- both raise
   the same `PlaywrightTimeoutError` otherwise. Re-ran the exact
   fault-injection scenario that first caught it 25 times in a row after
   the fix: zero failures (was failing roughly 1 in 5 before).

Neither bug was reachable by construction from Phase 3/4's own test
suites (which never drove the shell page's nested iframes or repeated a
navigating click enough times to hit the race) -- concrete evidence for
why Phase 5's live integration tier, reusing the exact same artifact
proven against fakes, earns its cost rather than being redundant with
the unit tier.

## 4. Heterogeneity & multi-tenant

*(pending)*

## 5. Escalation & handoff

*(pending)*

## 6. Safety

`cua.policy` sits *around* `cua.replay`, never inside it: the engine
(Section 3) carries zero vocabulary for domains or risk levels, only one
seam, an optional `guard: PolicyGuard | None` on `replay()`. A guard is
`(Step, Observation) -> PolicyDecision`, called fresh -- a real, current
`observe()`, never the artifact's static declarations -- immediately
before *any* step would otherwise act (NAVIGATE included), and a
decline stops that step's action from ever reaching the `Surface`,
coming back as a new taxonomy member, `ReplayStatus.POLICY_BLOCKED`
(added to `_ESCALATING` alongside `RECOVERABLE`/`HARD_FAILURE`
/`UNRECOGNIZED` -- a policy block is exactly the point a human should be
looped in, per the assignment's escalation requirement). With no guard
(the default, unchanged from Phase 5), every step runs exactly as
before; this is what let the change to `cua.replay.engine` stay a few
lines, additive, and fully backward compatible with every existing
Phase 5 test.

`cua.policy.build_default_guard(artifact, *, authorized_step_ids=...)`
builds the real guard from two independent checks, domain first so a
step that's both off-allowlist and risky reports the more fundamental
problem:

1. **Runtime domain allowlist enforcement.** `CapabilityArtifact`'s own
   validator (Section 2) already checks `policy_scope
   .allowed_action_types` covers every action type the recorded steps
   use -- but only structurally, against the document itself, once, at
   construction time. It has no way to know what domain a step will
   *actually* be running against when replayed later against a
   possibly-different tenant, environment, or (if something upstream
   went wrong) an unexpected redirect. The guard closes that gap:
   `urlsplit(observation.url).netloc` is checked against
   `policy_scope.allowed_domains` before *every* step, not just the
   first, since a multi-step flow can legitimately be several hops away
   from wherever it started.
2. **`RiskLevel.RISKY_IRREVERSIBLE` gating.** Declined by default. Which
   specific risky step is safe to run is a decision about *this
   invocation* -- did a human already approve opening *this* account
   for *this* member -- never a permanent, blanket property of the
   artifact document. So authorization is a caller-supplied
   `frozenset[str]` of step ids for one call (`guarded_replay(...,
   authorized_step_ids=frozenset({"click_confirm"}))`), not an artifact
   field and not a boolean that would authorize every risky step in the
   flow at once.

Proven live against the real target app (`tests/integration/policy`,
using `build_open_subaccount_artifact()` -- the search -> detail ->
open-sub-account -> confirm flow, whose final commit is tagged
`RISKY_IRREVERSIBLE` per Section 1's own note that this is exactly the
action a recorded capability should stop short of by default): an
unauthorized run is blocked at `click_confirm` and the browser is left
sitting on the confirm screen, never the success page, proving the
commit genuinely never fired rather than merely being reported as
skipped; the same artifact with `click_confirm` explicitly authorized
reaches `SUCCESS` and the real success page; and a deliberately
mismatched `allowed_domains` blocks at the very first step, before the
first `NAVIGATE` ever runs. All three passed cleanly across 5 repeated
runs.

Runtime redaction is the third piece, and deliberately separate from
both of the above: `cua.policy.redact_result(artifact, raw_inputs,
result)` is a pure function producing a log/evidence-safe projection of
one invocation's actual data. Phase 1's `CapabilityArtifact
.to_log_safe_dict()` already redacts the recorded *document*
(discovery-time DOM snippets baked into the artifact); this redacts
what actually happened during *this run* -- the raw inputs a caller
supplied and the raw outputs captured -- using the exact same
`sensitive` declarations on `ParamSpec`/`OutputSpec`, so a sensitive
value doesn't reach a log or evidence sink in the clear just because it
came from a live run rather than the static artifact. `last_observation`
is dropped from the projection entirely, not masked field by field --
see Section 7.

## 7. Cuts

- Tier 4 locator strategy (`VISUAL_TEMPLATE`) is schema-validated but not
  executed by the replay engine (Section 1).
- The desktop surface is an interface stub (Section 1); operator console
  is still to come and will be a minimal/mocked UI (Section 5).
- The replay engine's `EXTRACT` action never coerces the raw extracted
  string against the declared `OutputSpec.type` -- `"$4,231.50"` comes
  back exactly as read, not as a parsed `4231.50`. Generic text-to-type
  coercion for arbitrary legacy UI formatting (currency, thousands
  separators, locale-specific decimals) is real work with real edge
  cases of its own; the type on `OutputSpec` documents the caller's
  contract, but parsing that raw string is left to the caller/consumer,
  not silently attempted here.
- The replay engine never attempts automatic recovery from a
  `recoverable` `KnownOutcome` (e.g. dismissing a surprise dialog and
  resuming the flow) -- it only detects and classifies correctly (Section
  3). Deciding what to do about a recoverable stop is the agent loop's
  and escalation layer's job, not this executor's.
- `authorized_step_ids` is a plain, caller-trusted set for one call --
  there's no signature, ticket, or audit trail proving a human actually
  approved it (Section 6). That belongs to whatever calls `cua.policy`
  (the escalation layer, Phase 8) once a human has actually signed off
  in a UI; this layer's job is only to refuse to proceed without it.
- The domain allowlist is checked against `Observation.url` -- what the
  browser is actually showing -- not enforced at the network layer
  (Section 6). A surface that could be tricked into rendering
  attacker-controlled content at an allowed-looking URL (e.g. an open
  redirect on the target app itself) is outside this guard's reach; it
  guards against the artifact/invocation going somewhere it wasn't
  meant to, not against the target app's own vulnerabilities.
- `redact_result`'s projection drops `last_observation` entirely rather
  than redacting it field by field (Section 6): an `Observation`'s
  accessible-name text has no declared field boundary to redact
  against, the same reasoning `to_log_safe_dict()`'s own docstring gives
  for leaving screenshot redaction to a lower layer (`cua.evidence`,
  still to come). A caller that logs `last_observation` separately must
  apply its own judgment.
