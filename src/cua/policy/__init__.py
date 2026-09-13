"""Policy & safety: sits around `cua.replay`, never inside it.

- `cua.policy.guard.build_default_guard` turns an artifact's own
  `policy_scope` plus a per-invocation authorization set into the real
  `PolicyGuard` that `cua.replay.replay`'s optional `guard` seam calls.
- `cua.policy.enforce.guarded_replay` is the one-call ergonomic wrapper
  most callers should use instead of calling `cua.replay.replay`
  directly.
- `cua.policy.redact.redact_result` produces a log/evidence-safe
  projection of one invocation's actual inputs/outputs.

`PolicyDecision`/`PolicyGuard` are re-exported here from
`cua.replay.contract` for convenience -- they're the shared vocabulary
between the two modules, but they're owned by `cua.replay` (see that
module for why).
"""
from cua.policy.enforce import guarded_replay
from cua.policy.guard import build_default_guard
from cua.policy.redact import redact_result
from cua.replay.contract import PolicyDecision, PolicyGuard

__all__ = [
    "PolicyDecision",
    "PolicyGuard",
    "build_default_guard",
    "guarded_replay",
    "redact_result",
]
