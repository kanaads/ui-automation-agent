"""Builds the real `PolicyGuard` that `cua.replay.engine.replay`'s
`guard` seam calls before every step.

Two independent checks, in a fixed order (domain first, so a
step-off-the-allowlist and a risky-step both being true reports the
more fundamental problem):

1. Runtime domain allowlist enforcement. `CapabilityArtifact`'s own
   validator (Phase 1) already checks that `policy_scope
   .allowed_action_types` covers every action type the recorded steps
   use -- but only *structurally*, against the artifact document
   itself, once, at construction time. It has no way to know what
   domain a step will actually be running against when replayed later
   -- that's runtime information. This guard closes that gap: every
   single step, re-checked against a fresh `Observation.url` right
   before it would act, not just the first one and not just once.
   That matters because a step could legitimately be several hops (and
   possibly redirects) away from wherever the artifact started.

2. `RiskLevel.RISKY_IRREVERSIBLE` step gating. Which specific risky
   step is safe to run is a decision about *this invocation* -- did a
   human already approve opening *this* account for *this* member --
   never a blanket, permanent property of the artifact document. So
   authorization is scoped to a caller-supplied set of step ids for
   one call, not a flag baked into the artifact or held across calls.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from cua.artifact.models import CapabilityArtifact, RiskLevel, Step
from cua.replay.contract import PolicyDecision, PolicyGuard
from cua.surface.models import Observation


def build_default_guard(
    artifact: CapabilityArtifact, *, authorized_step_ids: frozenset[str] = frozenset()
) -> PolicyGuard:
    def guard(step: Step, observation: Observation) -> PolicyDecision:
        domain = _domain_of(observation.url)
        if not _domain_allowed(domain, artifact.policy_scope.allowed_domains):
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"observed domain '{domain}' is not in policy_scope.allowed_domains "
                    f"{artifact.policy_scope.allowed_domains}"
                ),
            )

        if step.risk == RiskLevel.RISKY_IRREVERSIBLE and step.step_id not in authorized_step_ids:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"step '{step.step_id}' is risk=risky_irreversible and was not authorized "
                    f"for this invocation ({step.risk_rationale or 'no rationale recorded'})"
                ),
            )

        return PolicyDecision(allowed=True)

    return guard


def _domain_of(url: str) -> str:
    return urlsplit(url).netloc


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    return "*" in allowed_domains or domain in allowed_domains
