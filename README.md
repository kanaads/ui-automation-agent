# Computer-Use Automation System

> Status: in progress. This README is being filled in phase by phase; see
> `REPORT.md` for the design write-up (also in progress).

An LLM drives a real UI once to accomplish a goal, records what it did as a
typed, reviewable **Capability Artifact**, and replays that artifact
deterministically afterward with no model in the decision loop. When
either path gets stuck, control hands off to a human on the *same* live
session.

Built against a self-authored "hostile legacy" credit-union back office
(framesets, table layout, no test IDs, injectable runtime faults) rather
than a clean modern demo site — see `REPORT.md` Section 4 for why.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
make install     # pip install -e ".[dev]"
make browsers    # playwright install --with-deps chromium
```

If `make browsers` succeeds but launching Chromium still fails with a
missing-shared-library error (seen in some locked-down containers without
`sudo`) and you can't run `playwright install-deps`, it's almost always
one library (commonly `libXdamage.so.1`). You can fetch just that .deb
without root and point the loader at it:

```bash
apt-get download libxdamage1
dpkg-deb -x libxdamage1_*.deb /tmp/extra-libs
export LD_LIBRARY_PATH=/tmp/extra-libs/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
```

(adjust the architecture directory name to match `uname -m`.) A normal
dev machine or CI runner with `sudo` (this repo's GitHub Actions workflow
included) never needs this.

Copy `.env.example` to `.env` if you intend to run the live discovery step
(`make evidence-run`). No `.env` is required to run the test suite —
`tests/unit` and `tests/integration` never call a real LLM provider.

## Running the tests

```bash
make unit          # fast, no browser, no network
make integration   # real Playwright browser + local fake app; LLM calls
                    # use a fixture/replay transcript, never a live model
```

`tests/e2e_live` is excluded from both; it costs real API tokens and is run
manually (see the demo path below).

## Demo path

*(to be filled in fully as each phase lands — discovery run, artifact
replay, error-path replay, and escalation/handoff commands)*

The proxy target ("Meridian Core", a deliberately hostile legacy
credit-union back office) can already be run standalone:

```bash
make run-app        # serves it at http://localhost:8000
```

Open `http://localhost:8000/app` in a browser to explore the search →
detail and open-sub-account → confirm flows by hand. `/debug/faults/arm`
(see `src/cua/target_app/faults.py`) lets you inject a session timeout,
permission denial, slow load, surprise interstitial, or forced validation
error on a specific route for your session — that's exactly what the
replay engine's error taxonomy (`cua.replay`, REPORT.md Section 3) is
tested against, including live, both with and without a fault armed:

```python
from cua.replay import replay
from cua.surface.web import WebSurface
from tests.unit.replay.conftest import build_member_balance_artifact
# with a real Playwright `page` already on this app's origin:
result = replay(build_member_balance_artifact(), {"member_id": "10001"}, WebSurface(page))
print(result.status, result.outputs)  # ReplayStatus.SUCCESS {'balance_text': '$4,231.50'}
```

`cua.policy.guarded_replay` is the safety-gated equivalent most callers
should reach for instead of `cua.replay.replay` directly (REPORT.md
Section 6): it stops a `RiskLevel.RISKY_IRREVERSIBLE` step (e.g. the
open-sub-account flow's final "Confirm & Open Account" commit) unless
its step id is explicitly authorized for that call, and blocks outright
if the surface has drifted off the artifact's own domain allowlist.

```python
from cua.policy import guarded_replay
from cua.surface.web import WebSurface
from tests.integration.policy.conftest import build_open_subaccount_artifact

surface = WebSurface(page)
inputs = {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"}

blocked = guarded_replay(build_open_subaccount_artifact(), inputs, surface)
print(blocked.status)  # ReplayStatus.POLICY_BLOCKED -- commit was never attempted

opened = guarded_replay(
    build_open_subaccount_artifact(), inputs, surface, authorized_step_ids=frozenset({"click_confirm"})
)
print(opened.status)  # ReplayStatus.SUCCESS -- explicitly authorized this time
```

`cua.agent.discover` is the LLM-driven half: it drives a live `Surface`
one perceive-decide-act step at a time (no artifact yet) until the model
reports the goal reached, reports itself stuck, or `max_steps` runs out
(REPORT.md Section 1). `cua.agent.recorder.build_artifact_from_discovery`
then turns a successful transcript into a reviewable `CapabilityArtifact`
— the same shape `cua.replay.replay` executes with no model involved:

```python
from cua.agent.discover import discover
from cua.agent.recorder import build_artifact_from_discovery
from cua.artifact.models import Checkpoint, LocatorStrategy, LocatorTier, ParamSpec, ParamType, ProvenanceRecordedBy, TenantScope
from cua.surface.web import WebSurface
from datetime import datetime, timezone

surface = WebSurface(page)  # a real Playwright `page`, already on this app's origin
llm = build_llm_client_from_env()  # or any LLMClient — Groq/NVIDIA NIM/Bedrock

result = discover("Look up member 10001 and open their detail page.", surface, llm)
print(result.status)  # DiscoveryStatus.GOAL_REACHED

artifact = build_artifact_from_discovery(
    result,
    capability_id="look_up_member", version="1.0.0",
    description="Look up a member by id and open their detail page.",
    tenant_scope=TenantScope(vendor_app_id="meridian_core"),
    checkpoint=Checkpoint(
        description="The member detail page is showing.",
        detection=LocatorTier(strategy=LocatorStrategy.ROLE_NAME, params={"role": "heading", "name": "Member Detail"}),
    ),
    input_schema=[ParamSpec(name="member_id", type=ParamType.STRING, required=True)],
    parameterize={"10001": "member_id"},  # the literal discovery typed -> the parameter it becomes
    provenance=ProvenanceRecordedBy(kind="llm_discovery", recorded_at=datetime.now(timezone.utc)),
)
# artifact is now replayable deterministically, for a different member id,
# with no model in the loop at all: replay(artifact, {"member_id": "10002"}, WebSurface(other_page))
```

When either path ends in a status that needs a human
(`result.needs_escalation`), `cua.escalation.trigger` turns it into a
`HandoffTicket` on a real queue, and `cua.escalation.handoff` is what
lets that human join the *exact same* live browser tab rather than a
fresh one — the marker survives the human navigating around, so it
works mid-flow, not just at a clean stopping point:

```python
from cua.escalation import (
    InMemoryEscalationQueue, mark_page_for_handoff, reconnect_to_marked_page,
    ticket_from_replay, SessionHandle,
)

# `page` is on whatever screen the run stopped at; `cdp_endpoint` is
# wherever this browser process was launched with a remote-debugging
# port exposed (e.g. `chromium.launch(args=["--remote-debugging-port=9333"])`).
marker = mark_page_for_handoff(page)
ticket = ticket_from_replay(result, artifact=artifact, raw_inputs=inputs, session=SessionHandle(cdp_endpoint, marker))

queue = InMemoryEscalationQueue()
if ticket is not None:
    queue.open(ticket)

# From a SEPARATE process/script -- a human operator's own tooling:
joined_page = reconnect_to_marked_page(marker, cdp_endpoint=cdp_endpoint, connect_over_cdp=playwright.chromium.connect_over_cdp)
# ...human does whatever's needed on `joined_page`, the real live tab...
queue.resolve(ticket.ticket_id, notes="opened the account manually after review")
```

## Repository layout

```
src/cua/
  artifact/     the Capability Artifact schema (the contract)
  surface/      perception/action abstraction over a UI surface
  locator/      tiered, fallback-ordered element targeting
  replay/       deterministic executor + error taxonomy
  policy/       allowlist, risk classification, redaction
  agent/        LLM-driven discovery loop + recorder
  escalation/   ticket/queue state machine + same-live-session CDP handoff
  target_app/   the local "hostile legacy" proxy target
  evidence/     structured run logging / evidence capture
tests/
  unit/         no browser, no network
  integration/  real browser + local app, LLM calls are fixture-driven
  e2e_live/     real LLM provider against a live browser session
evidence/       saved discovery + replay run evidence (Section 6 deliverable)
```
