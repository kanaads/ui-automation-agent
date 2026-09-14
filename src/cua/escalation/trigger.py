"""The glue that turns an escalating result -- from either
`cua.replay.replay()` or `cua.agent.discover.discover()` -- into a
`HandoffTicket` ready for `EscalationQueue.open()`. Both functions
return `None` outright when the result doesn't need escalation
(`ReplayResult.needs_escalation` / `DiscoveryResult.needs_escalation`):
there is nothing to raise a ticket about, and "None means don't
escalate" is a plainer contract for a caller than an empty or sentinel
ticket would be.

`ticket_from_replay` never re-implements redaction: it reuses
`cua.policy.redact_result` verbatim for `context`, so a sensitive input
or output never reaches a ticket in the clear just because the
sink is now a human-facing queue rather than a log, and
`last_observation` is dropped for exactly the reason
`redact_result`'s own docstring already gives (Section 6/7).

`ticket_from_discovery` has no artifact -- and therefore no `sensitive`
schema -- to redact against yet; discovery escalating is precisely the
situation where no artifact exists. Its context is kept to
non-content metadata only (the goal, the status, how many steps were
actually taken) and never includes the raw `final_observation` or
`transcript`, the same "never hand the raw perception to a
lower-trust sink" rule `redact_result` already applies once an
artifact does exist.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from cua.agent.contract import DiscoveryResult
from cua.artifact.models import CapabilityArtifact
from cua.escalation.contract import HandoffSource, HandoffTicket, SessionHandle
from cua.policy.redact import redact_result
from cua.replay.contract import ReplayResult


def ticket_from_replay(
    result: ReplayResult,
    *,
    artifact: CapabilityArtifact,
    raw_inputs: Mapping[str, Any],
    session: SessionHandle,
) -> HandoffTicket | None:
    if not result.needs_escalation:
        return None
    return HandoffTicket(
        ticket_id=str(uuid.uuid4()),
        source=HandoffSource.REPLAY,
        reason=result.reason,
        status_code=result.status.value,
        capability_id=artifact.capability_id,
        context=redact_result(artifact, raw_inputs, result),
        session=session,
    )


def ticket_from_discovery(result: DiscoveryResult, *, session: SessionHandle) -> HandoffTicket | None:
    if not result.needs_escalation:
        return None
    return HandoffTicket(
        ticket_id=str(uuid.uuid4()),
        source=HandoffSource.DISCOVERY,
        reason=result.reason,
        status_code=result.status.value,
        capability_id=None,
        context={"goal": result.goal, "status": result.status.value, "steps_taken": len(result.transcript)},
        session=session,
    )
