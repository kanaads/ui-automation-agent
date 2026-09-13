"""In-memory seed data for the target app.

All members are fabricated ("Test"/"Sample"/"Demo" in every name, on
purpose) and account numbers are fake. Nothing here is or resembles real
PII, per the assignment's ground rules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str
    savings_balance_cents: int
    status: str = "ACTIVE"  # ACTIVE | CLOSED


def _default_members() -> dict[str, Member]:
    members = [
        Member(member_id="10001", name="Alice Testperson", savings_balance_cents=423150, status="ACTIVE"),
        Member(member_id="10002", name="Bob Sampleuser", savings_balance_cents=982, status="ACTIVE"),
        Member(member_id="10003", name="Carla Democustomer", savings_balance_cents=0, status="CLOSED"),
        Member(member_id="10004", name="Deshawn Testmember", savings_balance_cents=1500000, status="ACTIVE"),
    ]
    return {m.member_id: m for m in members}


class MemberStore:
    """Read-only lookup of seeded members. `reset()` restores the default
    seed, used to isolate tests/evidence runs from each other."""

    def __init__(self) -> None:
        self._members: dict[str, Member] = _default_members()

    def get(self, member_id: str) -> Member | None:
        return self._members.get(member_id)

    def all(self) -> list[Member]:
        return list(self._members.values())

    def reset(self) -> None:
        self._members = _default_members()


@dataclass(frozen=True)
class PendingSubAccount:
    member_id: str
    account_type: str
    initial_deposit_cents: int
    purpose: str


class PendingSubAccountStore:
    """Ephemeral, one-time-use tokens bridging the sub-account 'new' form
    to the 'confirm' screen and the final commit. A real system would sign
    this server-side state; a plain server-held dict is enough for a mock
    surface whose whole point is the UI automation problem, not session
    security.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingSubAccount] = {}

    def create(
        self, *, member_id: str, account_type: str, initial_deposit_cents: int, purpose: str
    ) -> str:
        token = uuid.uuid4().hex
        self._pending[token] = PendingSubAccount(
            member_id=member_id,
            account_type=account_type,
            initial_deposit_cents=initial_deposit_cents,
            purpose=purpose,
        )
        return token

    def get(self, token: str) -> PendingSubAccount | None:
        return self._pending.get(token)

    def consume(self, token: str) -> PendingSubAccount | None:
        return self._pending.pop(token, None)
