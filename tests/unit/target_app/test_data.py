"""In-memory seed data for the target app. All members are obviously
fake -- no real names, no real account numbers -- per the assignment's
ground rule to never use real PII, even in a mock.
"""
import pytest

from cua.target_app.data import Member, MemberStore, PendingSubAccountStore

pytestmark = pytest.mark.unit


class TestMemberStore:
    def test_seeded_member_is_retrievable(self):
        store = MemberStore()
        member = store.get("10001")
        assert member is not None
        assert isinstance(member, Member)
        assert member.member_id == "10001"

    def test_unknown_member_id_returns_none(self):
        store = MemberStore()
        assert store.get("99999999") is None

    def test_seed_includes_at_least_one_closed_member(self):
        """Needed to exercise a business outcome beyond plain not-found,
        e.g. a permission/eligibility check on a closed account."""
        store = MemberStore()
        assert any(m.status == "CLOSED" for m in store.all())

    def test_seed_includes_at_least_one_active_member_with_positive_balance(self):
        store = MemberStore()
        assert any(m.status == "ACTIVE" and m.savings_balance_cents > 0 for m in store.all())

    def test_reset_restores_default_seed(self):
        store = MemberStore()
        original_count = len(store.all())
        store.reset()
        assert len(store.all()) == original_count
        assert store.get("10001") is not None

    def test_seeded_names_are_obviously_fake(self):
        """A light guard against ever seeding anything resembling real PII."""
        store = MemberStore()
        for m in store.all():
            assert m.name  # non-empty
            assert "Test" in m.name or "Sample" in m.name or "Demo" in m.name


class TestPendingSubAccountStore:
    def test_create_returns_a_token_and_stores_the_request(self):
        store = PendingSubAccountStore()
        token = store.create(
            member_id="10001", account_type="SAVINGS", initial_deposit_cents=5000, purpose="Test"
        )
        assert token
        pending = store.get(token)
        assert pending is not None
        assert pending.member_id == "10001"
        assert pending.account_type == "SAVINGS"

    def test_get_unknown_token_returns_none(self):
        store = PendingSubAccountStore()
        assert store.get("not-a-real-token") is None

    def test_consume_removes_the_entry_one_time_use(self):
        store = PendingSubAccountStore()
        token = store.create(
            member_id="10001", account_type="SAVINGS", initial_deposit_cents=5000, purpose="Test"
        )
        first = store.consume(token)
        assert first is not None
        assert store.consume(token) is None

    def test_tokens_are_unique_per_request(self):
        store = PendingSubAccountStore()
        t1 = store.create(member_id="10001", account_type="SAVINGS", initial_deposit_cents=5000, purpose="a")
        t2 = store.create(member_id="10001", account_type="SAVINGS", initial_deposit_cents=5000, purpose="b")
        assert t1 != t2
