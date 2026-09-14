"""What makes "hand off to a human on the *same* live session" concrete
rather than aspirational: a *separate* process (a human operator's own
tooling -- never this one) attaching to the exact running browser over
the Chrome DevTools Protocol and finding the exact tab discovery or
replay was just driving, cookies, in-progress form state, and all.

Two functions, deliberately small and symmetric:

`mark_page_for_handoff(page)` writes a fresh, random, disposable marker
onto the live page's own `window` object and returns it.
`reconnect_to_marked_page(marker, ...)` -- called from a *different*
script/process holding its own Playwright driver -- connects to the
browser via CDP and searches every open context and page for that
marker, returning the first live `Page` that carries it.

Matching on an injected marker rather than, say, the page's current URL
is deliberate: a human might navigate around before or during a
handoff (or the flow might have several steps left on the same tab),
and the marker survives that so long as the page itself isn't replaced
-- a URL match would not.

`connect_over_cdp` is always the caller's own bound method (typically
`playwright.chromium.connect_over_cdp` from an already-running
Playwright driver session) -- this module never starts or owns a
driver of its own, the same "the caller owns lifecycle" rule
`cua.surface.base.Surface` already documents for its own callers, and
the same injectable-collaborator pattern `cua.agent.llm`'s provider
clients use for their own network boundary (`http_client`,
`bedrock_runtime_client`) -- which is also what keeps this module's own
unit tests real-browser-free (see tests/unit/escalation/test_handoff.py);
the genuine two-connection reconnect is proven live in
tests/integration/escalation/test_handoff_live.py.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from playwright.sync_api import Error as PlaywrightError

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

_SET_MARKER_SCRIPT = "(m) => { window.__cua_handoff_marker = m; }"
_GET_MARKER_SCRIPT = "() => window.__cua_handoff_marker"


class PageNotFoundError(RuntimeError):
    """No open page across every context of the reconnected browser
    carried the expected marker within `timeout_s` -- the marker was
    never set, the page was closed or replaced, or the wrong browser/
    endpoint was given."""


class _EvaluatablePage(Protocol):
    def evaluate(self, script: str, arg: object = None) -> object: ...


def mark_page_for_handoff(page: _EvaluatablePage) -> str:
    marker = uuid.uuid4().hex
    page.evaluate(_SET_MARKER_SCRIPT, marker)
    return marker


def reconnect_to_marked_page(
    marker: str,
    *,
    cdp_endpoint: str,
    connect_over_cdp: Callable[[str], Browser],
    poll_interval_s: float = 0.1,
    timeout_s: float = 10.0,
) -> Page:
    browser = connect_over_cdp(cdp_endpoint)
    deadline = time.monotonic() + timeout_s

    while True:
        for context in browser.contexts:
            for page in context.pages:
                try:
                    found = page.evaluate(_GET_MARKER_SCRIPT)
                except PlaywrightError:
                    continue  # a closed or mid-navigation page -- keep looking, don't fail the search
                if found == marker:
                    return page
        if time.monotonic() >= deadline:
            raise PageNotFoundError(f"no open page carried handoff marker '{marker}' within {timeout_s}s")
        time.sleep(poll_interval_s)
