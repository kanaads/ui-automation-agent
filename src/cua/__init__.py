"""cua: Computer-Use Automation System.

Discovery (LLM-driven observe/decide/act) records a reusable, typed
Capability Artifact. Replay executes that artifact deterministically,
with no model in the decision loop. Escalation hands the live session
to a human when either path gets stuck.

Package map:
    artifact     - the Capability Artifact schema (the contract)
    surface      - perception/action abstraction over a UI surface
    locator      - tiered, fallback-ordered element targeting
    replay       - deterministic executor + error taxonomy
    policy       - allowlist, risk classification, redaction
    agent        - LLM-driven discovery loop + recorder
    escalation   - control-transfer state machine + operator handoff
    target_app   - the local "hostile legacy" proxy target
    evidence     - structured run logging / evidence capture
"""

__version__ = "0.1.0"
