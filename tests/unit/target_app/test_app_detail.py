import pytest

pytestmark = pytest.mark.unit


def test_detail_shows_name_and_formatted_balance(client):
    resp = client.get("/content/detail", params={"id": "10001"})
    assert resp.status_code == 200
    assert "Alice Testperson" in resp.text
    assert "$4,231.50" in resp.text
    assert "Member Detail" in resp.text  # checkpoint heading


def test_detail_has_open_subaccount_link(client):
    resp = client.get("/content/detail", params={"id": "10001"})
    assert 'href="/content/subaccount/new?id=10001"' in resp.text
    assert "Open Sub-Account" in resp.text


def test_detail_for_unknown_id_falls_back_to_not_found(client):
    resp = client.get("/content/detail", params={"id": "00000000"})
    assert resp.status_code == 200
    assert "No records match your search." in resp.text


def test_zero_balance_member_renders_correctly(client):
    resp = client.get("/content/detail", params={"id": "10003"})
    assert "$0.00" in resp.text
    assert "CLOSED" in resp.text
