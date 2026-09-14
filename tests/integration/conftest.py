"""Shared fixtures for integration tests: a real Playwright browser
driving a real, freshly-started instance of the target app over real
HTTP. No LLM calls happen at this tier -- see tests/e2e_live for that.
"""
import os
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from cua.target_app.app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_app():
    """A fresh target-app instance (base tenant), isolated per test."""
    port = _free_port()
    app = create_app(tenant_variant="base")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture()
def live_tenant_b_app():
    port = _free_port()
    app = create_app(tenant_variant="tenant_b")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def playwright_instance():
    """The one Playwright driver connection this whole test session is
    allowed to have: its sync API raises outright if a second
    `sync_playwright()` is entered while one is already active in this
    process (confirmed directly -- it's not a pytest-asyncio artifact).
    Any fixture that needs its own `Browser` with non-default launch
    args (e.g. `tests/integration/escalation/conftest.py`'s CDP-enabled
    one) depends on this shared instance rather than starting another.
    """
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    # Default is headless (CI / test.bat). Set HEADED=1 to watch the UI;
    # optional SLOW_MO (ms) slows each action so the run is visible.
    headed = os.environ.get("HEADED", "").strip().lower() in ("1", "true", "yes")
    slow_mo = int(os.environ.get("SLOW_MO", "0") or "0")
    b = playwright_instance.chromium.launch(headless=not headed, slow_mo=slow_mo)
    yield b
    b.close()


@pytest.fixture()
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()
