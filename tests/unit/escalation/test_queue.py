"""cua.escalation.queue.InMemoryEscalationQueue: the operator-facing
state machine around a HandoffTicket. OPEN -> CLAIMED -> {RESOLVED,
ABANDONED}, with CLAIMED skippable (a human can resolve/abandon
directly from OPEN) but every other transition rejected outright --
never silently coerced or ignored, the same "a state nobody declared
is an error, not a guess" philosophy `cua.replay.engine` and
`cua.locator.resolve_target` already apply to their own state.
"""
import pytest

from cua.escalation.contract import HandoffSource, HandoffStatus, HandoffTicket, SessionHandle
from cua.escalation.queue import HandoffStateError, InMemoryEscalationQueue, TicketNotFoundError

pytestmark = pytest.mark.unit


def _ticket(ticket_id: str = "t1") -> HandoffTicket:
    return HandoffTicket(
        ticket_id=ticket_id,
        source=HandoffSource.REPLAY,
        reason="policy blocked",
        status_code="policy_blocked",
        capability_id="open_subaccount",
        context={"foo": "bar"},
        session=SessionHandle(),
    )


def test_open_then_get_returns_the_same_ticket():
    queue = InMemoryEscalationQueue()
    ticket = _ticket()

    queue.open(ticket)

    assert queue.get("t1") is ticket


def test_get_on_an_unknown_ticket_id_returns_none():
    queue = InMemoryEscalationQueue()

    assert queue.get("nope") is None


def test_opening_a_duplicate_ticket_id_raises():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket("t1"))

    with pytest.raises(HandoffStateError, match="already exists"):
        queue.open(_ticket("t1"))


def test_opening_a_ticket_not_in_open_status_raises():
    queue = InMemoryEscalationQueue()
    ticket = _ticket()
    ticket.status = HandoffStatus.RESOLVED

    with pytest.raises(HandoffStateError, match="OPEN"):
        queue.open(ticket)


def test_list_open_includes_open_and_claimed_but_not_resolved_or_abandoned():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket("open1"))
    queue.open(_ticket("claimed1"))
    queue.claim("claimed1", operator="ops1")
    queue.open(_ticket("resolved1"))
    queue.resolve("resolved1", notes="fixed")
    queue.open(_ticket("abandoned1"))
    queue.abandon("abandoned1", notes="gave up")

    open_ids = {t.ticket_id for t in queue.list_open()}

    assert open_ids == {"open1", "claimed1"}


def test_claim_sets_status_and_operator():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())

    claimed = queue.claim("t1", operator="ops1")

    assert claimed.status == HandoffStatus.CLAIMED
    assert claimed.claimed_by == "ops1"
    assert queue.get("t1").claimed_by == "ops1"  # same mutated object, not a copy


def test_claim_on_an_already_claimed_ticket_raises():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())
    queue.claim("t1", operator="ops1")

    with pytest.raises(HandoffStateError, match="OPEN"):
        queue.claim("t1", operator="ops2")


def test_claim_on_an_unknown_ticket_raises_ticket_not_found():
    queue = InMemoryEscalationQueue()

    with pytest.raises(TicketNotFoundError, match="nope"):
        queue.claim("nope", operator="ops1")


@pytest.mark.parametrize("starting_status", [HandoffStatus.OPEN, HandoffStatus.CLAIMED])
def test_resolve_is_allowed_from_open_or_claimed(starting_status):
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())
    if starting_status == HandoffStatus.CLAIMED:
        queue.claim("t1", operator="ops1")

    resolved = queue.resolve("t1", notes="opened the account manually")

    assert resolved.status == HandoffStatus.RESOLVED
    assert resolved.resolution_notes == "opened the account manually"
    assert resolved.resolved_at is not None


def test_resolve_on_an_already_resolved_ticket_raises():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())
    queue.resolve("t1", notes="done")

    with pytest.raises(HandoffStateError, match="RESOLVED"):
        queue.resolve("t1", notes="done again")


def test_resolve_on_an_unknown_ticket_raises_ticket_not_found():
    queue = InMemoryEscalationQueue()

    with pytest.raises(TicketNotFoundError):
        queue.resolve("nope", notes="")


@pytest.mark.parametrize("starting_status", [HandoffStatus.OPEN, HandoffStatus.CLAIMED])
def test_abandon_is_allowed_from_open_or_claimed(starting_status):
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())
    if starting_status == HandoffStatus.CLAIMED:
        queue.claim("t1", operator="ops1")

    abandoned = queue.abandon("t1", notes="no longer relevant")

    assert abandoned.status == HandoffStatus.ABANDONED
    assert abandoned.resolution_notes == "no longer relevant"
    assert abandoned.resolved_at is not None


def test_abandon_on_an_already_abandoned_ticket_raises():
    queue = InMemoryEscalationQueue()
    queue.open(_ticket())
    queue.abandon("t1", notes="")

    with pytest.raises(HandoffStateError, match="ABANDONED"):
        queue.abandon("t1", notes="again")


def test_abandon_on_an_unknown_ticket_raises_ticket_not_found():
    queue = InMemoryEscalationQueue()

    with pytest.raises(TicketNotFoundError):
        queue.abandon("nope", notes="")
