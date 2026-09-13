import pytest

from cua.target_app.state import AppState

pytestmark = pytest.mark.unit


def test_fresh_with_unknown_tenant_variant_raises():
    with pytest.raises(ValueError, match="unknown tenant_variant"):
        AppState.fresh("not_a_real_tenant")


def test_fresh_base_and_tenant_b_have_distinct_branding():
    base = AppState.fresh("base")
    tenant_b = AppState.fresh("tenant_b")
    assert base.branding != tenant_b.branding
