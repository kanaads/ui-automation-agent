"""The /debug/* surface is test/evidence-capture infrastructure, not part
of the agent-facing app -- Phase 6's allowlist explicitly excludes it.
These tests just confirm the control endpoints work in isolation from any
specific fault scenario (covered in test_app_faults.py).
"""
import pytest

pytestmark = pytest.mark.unit


def test_list_faults_reflects_arm(client):
    client.get("/content/search")
    client.post("/debug/faults/arm", json={"hook": "detail", "code": "permission_denied", "occurrences": 2})
    resp = client.get("/debug/faults")
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"][0]["code"] == "permission_denied"
    assert body["detail"][0]["occurrences"] == 2


def test_clear_specific_hook(client):
    client.get("/content/search")
    client.post("/debug/faults/arm", json={"hook": "detail", "code": "permission_denied"})
    client.post("/debug/faults/arm", json={"hook": "search", "code": "session_timeout"})
    client.post("/debug/faults/clear", json={"hook": "detail"})
    body = client.get("/debug/faults").json()
    assert "detail" not in body
    assert "search" in body


def test_clear_all(client):
    client.get("/content/search")
    client.post("/debug/faults/arm", json={"hook": "detail", "code": "permission_denied"})
    client.post("/debug/faults/clear", json={})
    body = client.get("/debug/faults").json()
    assert body == {}


def test_reset_restores_clean_member_and_fault_state(client):
    client.get("/content/search")
    client.post("/debug/faults/arm", json={"hook": "detail", "code": "permission_denied"})
    client.post("/debug/reset")
    body = client.get("/debug/faults").json()
    assert body == {}
    # member data is still there (reset re-seeds, doesn't wipe)
    resp = client.get("/content/detail", params={"id": "10001"})
    assert "Alice Testperson" in resp.text


def test_invalid_hook_value_is_rejected_with_a_clear_error(client):
    resp = client.post("/debug/faults/arm", json={"hook": "not_a_real_hook", "code": "session_timeout"})
    assert resp.status_code == 422
