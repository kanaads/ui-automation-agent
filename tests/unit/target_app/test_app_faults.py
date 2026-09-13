"""End-to-end (within the app) proof that each fault actually manifests
on the real route it's armed against, and that the ones which should be
recoverable actually are when retried. This is the evidence base for the
'runtime errors and exceptional states' half of the assignment -- the
replay engine (later phases) is what's expected to detect and handle
these; this phase just proves the app can genuinely produce them on cue.
"""
import time

import pytest

pytestmark = pytest.mark.unit


def _arm(client, hook, code, **kwargs):
    body = {"hook": hook, "code": code, **kwargs}
    resp = client.post("/debug/faults/arm", json=body)
    assert resp.status_code == 200, resp.text


def test_session_timeout_on_detail_then_recovers_on_retry(client):
    # Touch the app once so a session cookie exists before arming.
    client.get("/content/search")
    _arm(client, "detail", "session_timeout")

    first = client.get("/content/detail", params={"id": "10001"})
    assert first.status_code == 200
    assert "Session Expired" in first.text
    assert "Alice Testperson" not in first.text  # real content withheld

    # one-shot: the same request retried now succeeds (recoverable)
    second = client.get("/content/detail", params={"id": "10001"})
    assert "Alice Testperson" in second.text


def test_permission_denied_on_detail_has_no_recovery_link(client):
    client.get("/content/search")
    _arm(client, "detail", "permission_denied")

    resp = client.get("/content/detail", params={"id": "10001"})
    assert "Access Denied" in resp.text
    assert "Alice Testperson" not in resp.text
    assert "<a " not in resp.text  # hard failure: nothing to click through


def test_session_timeout_on_get_search(client):
    """The fault hook applies to GET /content/search too, not just the
    POST submit -- e.g. simply loading the search page can hit a session
    timeout if the browser session has been idle."""
    client.get("/content/search")
    _arm(client, "search", "session_timeout")

    resp = client.get("/content/search")
    assert "Session Expired" in resp.text

    resp2 = client.get("/content/search")
    assert "Member Search" in resp2.text


def test_surprise_dialog_on_search_then_ok_proceeds(client):
    client.get("/content/search")
    _arm(client, "search", "surprise_dialog")

    resp = client.post("/content/search", data={"txtMemberId": "10001"}, follow_redirects=False)
    assert "Are you sure you want to continue?" in resp.text

    # dismissing it (retrying) now goes through normally
    resp2 = client.post("/content/search", data={"txtMemberId": "10001"}, follow_redirects=False)
    assert resp2.status_code == 303
    assert resp2.headers["location"] == "/content/detail?id=10001"


def test_slow_load_on_search_actually_delays_the_response(client):
    client.get("/content/search")
    _arm(client, "search", "slow_load", delay_ms=150)

    start = time.monotonic()
    resp = client.get("/content/search")
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed >= 0.15


def test_validation_error_can_be_forced_on_an_otherwise_valid_submission(client):
    client.get("/content/search")
    _arm(client, "subaccount_new_submit", "validation_error")

    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "100.00",  # otherwise perfectly valid
            "txtPurpose": "Vacation fund",
        },
    )
    assert resp.status_code == 200
    assert "Confirm New Sub-Account" not in resp.text
    assert "at least $25.00" in resp.text


def test_occurrences_two_fires_twice_before_recovering(client):
    client.get("/content/search")
    _arm(client, "detail", "session_timeout", occurrences=2)

    assert "Session Expired" in client.get("/content/detail", params={"id": "10001"}).text
    assert "Session Expired" in client.get("/content/detail", params={"id": "10001"}).text
    assert "Alice Testperson" in client.get("/content/detail", params={"id": "10001"}).text


def test_session_timeout_on_subaccount_new_submit(client):
    """The generic (non-VALIDATION_ERROR) fault path on a POST hook: the
    submission itself is intercepted before any form validation runs."""
    client.get("/content/search")
    _arm(client, "subaccount_new_submit", "session_timeout")

    resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "100.00",
            "txtPurpose": "Vacation fund",
        },
    )
    assert "Session Expired" in resp.text
    assert "Confirm New Sub-Account" not in resp.text


def test_permission_denied_on_subaccount_confirm(client):
    client.get("/content/search")
    new_resp = client.post(
        "/content/subaccount/new",
        data={
            "id": "10001",
            "selAcctType": "SAVINGS",
            "txtInitialDeposit": "100.00",
            "txtPurpose": "Vacation fund",
        },
    )
    token = new_resp.text.split('name="token" value="')[1].split('"')[0]

    _arm(client, "subaccount_confirm", "permission_denied")
    resp = client.post("/content/subaccount/confirm", data={"token": token})
    assert "Access Denied" in resp.text
    assert "Sub-Account Opened" not in resp.text


def test_two_sessions_do_not_share_armed_faults(client, tenant_b_client):
    """Sanity check that the session cookie -- not some shared global --
    is what scopes fault arming, using two independent TestClient
    instances (each with its own cookie jar) as a stand-in for two
    independent browser sessions."""
    client.get("/content/search")
    _arm(client, "detail", "permission_denied")

    other = tenant_b_client
    other.get("/content/search")
    resp = other.get("/content/detail", params={"id": "10001"})
    assert "Access Denied" not in resp.text
    assert "Alice Testperson" in resp.text
