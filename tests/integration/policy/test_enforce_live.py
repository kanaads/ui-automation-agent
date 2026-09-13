"""End-to-end proof that cua.policy genuinely stops a risky step against
the real, running target app -- not just against a fake Surface. Same
artifact (`build_open_subaccount_artifact`), same real WebSurface, same
live browser as every other integration tier; only the invocation
(authorized or not, on-allowlist or not) changes between tests.
"""
import pytest

from cua.policy import guarded_replay
from cua.replay import ReplayStatus
from cua.surface.web import WebSurface
from tests.integration.policy.conftest import build_open_subaccount_artifact

pytestmark = pytest.mark.integration


def test_an_unauthorized_risky_commit_is_blocked_and_never_hits_the_real_app(page, live_app):
    page.goto(f"{live_app}/nav")
    surface = WebSurface(page)
    artifact = build_open_subaccount_artifact()

    result = guarded_replay(
        artifact, {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"}, surface
    )

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "click_confirm"
    assert result.needs_escalation
    # the commit genuinely never fired: the browser is still sitting on
    # the confirm screen the guard stopped it at, not the success page
    assert result.last_observation is not None
    assert any(n.name == "Confirm New Sub-Account" for n in result.last_observation.nodes)
    assert not any(n.name == "Sub-Account Opened" for n in result.last_observation.nodes)


def test_authorizing_the_specific_step_id_lets_the_real_commit_through(page, live_app):
    page.goto(f"{live_app}/nav")
    surface = WebSurface(page)
    artifact = build_open_subaccount_artifact()

    result = guarded_replay(
        artifact,
        {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"},
        surface,
        authorized_step_ids=frozenset({"click_confirm"}),
    )

    assert result.status == ReplayStatus.SUCCESS
    assert not result.needs_escalation
    assert any(n.name == "Sub-Account Opened" for n in result.last_observation.nodes)


def test_an_off_allowlist_domain_blocks_before_the_first_navigate_ever_runs(page, live_app):
    page.goto(f"{live_app}/nav")
    surface = WebSurface(page)
    artifact = build_open_subaccount_artifact(allowed_domains=["some-other-tenant.example:9999"])

    result = guarded_replay(
        artifact, {"account_type": "SAVINGS", "initial_deposit": "50.00", "purpose": "Vacation fund"}, surface
    )

    assert result.status == ReplayStatus.POLICY_BLOCKED
    assert result.failed_step_id == "go_to_detail"
    assert "domain" in result.reason.lower()
    # still sitting wherever the bootstrap left it -- the navigate that
    # would have taken it to the detail page never ran either
    assert surface.current_url().endswith("/nav")
