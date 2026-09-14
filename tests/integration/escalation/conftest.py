"""A Chromium instance launched with a real, fixed remote-debugging
port -- the one piece none of the other integration tiers need, since
they never have to prove a *second*, independent process can attach to
the *same* running browser. `cua.escalation.handoff.reconnect_to_marked_page`
is exactly that second connection; this fixture is what gives a live
test something real to reconnect to.

Launched from the shared `playwright_instance` fixture
(tests/integration/conftest.py), never a fresh `sync_playwright()` of
its own: confirmed directly that a second, independent Playwright
driver connection cannot coexist with the first in one process
(`sync_playwright()` entered while another is already active raises
"It looks like you are using Playwright Sync API inside the asyncio
loop" -- a real Playwright constraint, not a red herring about
pytest-asyncio).
"""
import socket

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def cdp_browser(playwright_instance):
    """Yields `(playwright, browser, cdp_endpoint)` for one test: a
    fresh `Browser` (and CDP port) per test, from the one shared driver
    session. `playwright.chromium.connect_over_cdp` is a stable, real
    bound method either way; the point being proven in the tests that
    use this fixture is that the *browser process* itself is reachable
    as an independent CDP target, not that the Python object doing the
    reconnecting is a different one.
    """
    port = _free_port()
    browser = playwright_instance.chromium.launch(args=[f"--remote-debugging-port={port}"])
    try:
        yield playwright_instance, browser, f"http://127.0.0.1:{port}"
    finally:
        browser.close()
