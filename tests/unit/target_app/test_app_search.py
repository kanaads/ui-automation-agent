"""Search is the entry point of the flow: type a member number, submit,
land on the detail page -- or a legitimate 'no records match' outcome for
an unknown one. These are in-process HTTP tests (Starlette's TestClient,
no real socket, no browser) -- fast enough to mark `unit` per this repo's
marker semantics; real browser-driven tests against this same app arrive
in the integration tier once the Surface abstraction exists.
"""
import pytest

pytestmark = pytest.mark.unit


def test_root_redirects_to_the_shell(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/app"


def test_shell_loads_and_embeds_the_content_frame(client):
    resp = client.get("/app")
    assert resp.status_code == 200
    assert 'name="contentFrame"' in resp.text
    assert "/content/search" in resp.text


def test_search_form_has_no_test_ids_or_label_associations(client):
    """Guard against accidentally making the surface easy: the member
    number field must be identifiable only by nearby text, not by a
    clean id/name/label-for -- that's the whole point of this target."""
    resp = client.get("/content/search")
    assert resp.status_code == 200
    assert 'id="' not in resp.text
    assert "data-testid" not in resp.text
    assert "<label" not in resp.text
    assert 'name="txtMemberId"' in resp.text
    assert "Member Number" in resp.text


def test_search_button_has_an_accessible_name_from_its_value(client):
    resp = client.get("/content/search")
    assert 'name="btnSearch"' in resp.text
    assert 'value="Search"' in resp.text


def test_valid_search_redirects_to_detail(client):
    resp = client.post("/content/search", data={"txtMemberId": "10001"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/content/detail?id=10001"


def test_unknown_member_id_shows_not_found_banner_not_a_crash(client):
    resp = client.post("/content/search", data={"txtMemberId": "00000000"})
    assert resp.status_code == 200
    assert "No records match your search." in resp.text
    # still the same search form, not an error page
    assert 'name="txtMemberId"' in resp.text


def test_search_whitespace_is_trimmed(client):
    resp = client.post("/content/search", data={"txtMemberId": "  10001  "}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/content/detail?id=10001"
