"""Two 'tenants' running the same underlying app, differently branded and
labeled -- a stand-in for the real environment's 'hundreds of tenants on
the same vendor product' (assignment Section 1/3.7). The search button's
accessible name deliberately differs between variants so a base-recorded
artifact's tier-1 locator provably misses on tenant_b, motivating the
fallback ladder / override story covered in the write-up.
"""
import pytest

pytestmark = pytest.mark.unit


def test_base_branding(client):
    resp = client.get("/nav")
    assert "Meridian Core Credit Union" in resp.text


def test_tenant_b_branding_differs(tenant_b_client):
    resp = tenant_b_client.get("/nav")
    assert "Second Story Federal Credit Union" in resp.text
    assert "Meridian Core Credit Union" not in resp.text


def test_search_button_label_differs_by_tenant(client, tenant_b_client):
    base_resp = client.get("/content/search")
    tenant_b_resp = tenant_b_client.get("/content/search")
    assert 'value="Search"' in base_resp.text
    assert 'value="Find Member"' in tenant_b_resp.text
    assert 'value="Search"' not in tenant_b_resp.text


def test_both_variants_share_the_same_field_names_and_structure(client, tenant_b_client):
    """The point of a shared vendor product: structure/field names are
    identical across tenants even though labels/branding differ."""
    base_resp = client.get("/content/search")
    tenant_b_resp = tenant_b_client.get("/content/search")
    assert 'name="txtMemberId"' in base_resp.text
    assert 'name="txtMemberId"' in tenant_b_resp.text


def test_both_variants_serve_the_same_seeded_member(client, tenant_b_client):
    base_resp = client.get("/content/detail", params={"id": "10001"})
    tenant_b_resp = tenant_b_client.get("/content/detail", params={"id": "10001"})
    assert "Alice Testperson" in base_resp.text
    assert "Alice Testperson" in tenant_b_resp.text
