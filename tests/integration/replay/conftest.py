"""Fixtures for driving cua.replay against the real target app + a real
browser, including real fault injection.

Arming a fault (`cua.target_app.faults.FaultController`) is per-session:
the debug endpoint keys off the `sid` cookie. `seeded_page` fixes that
cookie to a known value *before* the browser ever navigates, so a test
can `arm_fault()` over plain HTTP with the exact same `sid` the browser
will present -- otherwise the two would land in different, unrelated
sessions and the fault would silently never fire.
"""
from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.fixture()
def sid() -> str:
    return uuid.uuid4().hex


@pytest.fixture()
def seeded_page(page, sid, live_app):
    page.context.add_cookies([{"name": "sid", "value": sid, "url": live_app}])
    return page


def arm_fault(base_url: str, sid: str, hook: str, code: str, *, occurrences: int = 1, delay_ms: int = 0) -> None:
    response = httpx.post(
        f"{base_url}/debug/faults/arm",
        json={"hook": hook, "code": code, "occurrences": occurrences, "delay_ms": delay_ms},
        cookies={"sid": sid},
    )
    response.raise_for_status()
