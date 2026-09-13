import pytest
from fastapi.testclient import TestClient

from cua.target_app.app import create_app


@pytest.fixture()
def client() -> TestClient:
    """A fresh app (and therefore fresh member/pending/fault state) per
    test, using the base tenant branding. TestClient persists cookies
    across requests on the same instance, which is what lets our
    per-session fault arming work the same way a real browser session
    would."""
    return TestClient(create_app(tenant_variant="base"))


@pytest.fixture()
def tenant_b_client() -> TestClient:
    return TestClient(create_app(tenant_variant="tenant_b"))
