"""A minimal, rule-based stand-in for a real LLM, used only to drive
`cua.agent.discover` against the REAL target app end-to-end. A real
model is never called here (that's tests/e2e_live's job, and only
there) -- the point of THIS tier is to prove the loop's Surface-facing
mechanics (perceiving, mapping a decision to a real SurfaceAction,
re-observing) work against genuine, live-assigned refs that no
synthetic unit fixture can produce, the same reason
tests/integration/replay exists alongside tests/unit/replay.

Deliberately does NOT parse the rendered prompt text `discover()` sent
to a real LLMClient (fragile, and beside the point) -- it holds the
same `Surface` `discover()` is driving and re-observes it directly,
so it always sees the actual current refs, whatever they happen to be
this run.
"""
from __future__ import annotations

import json

from cua.agent.llm.base import LLMClient, LLMMessage
from cua.surface.base import Surface


class LookUpMemberScript(LLMClient):
    """Steps: type the member id -> click Search -> done, once the
    detail page's heading is visible. Raises loudly (via `next()`'s own
    StopIteration) if a step's expected element genuinely isn't there,
    rather than returning a decision referencing something that
    doesn't exist -- a bug in the fixture should fail obviously, not
    get silently reinterpreted as `discover()`'s own STUCK handling.
    """

    def __init__(self, surface: Surface, *, member_id: str = "10001") -> None:
        self._surface = surface
        self._member_id = member_id
        self._step = 0

    def complete(self, messages: list[LLMMessage]) -> str:
        self._step += 1
        observation = self._surface.observe()

        if self._step == 1:
            node = next(n for n in observation.nodes if n.role == "textbox" and n.frame == "contentFrame")
            return json.dumps(
                {"thought": "type the member id", "action": "type", "frame": node.frame, "ref": node.ref, "value": self._member_id}
            )

        if self._step == 2:
            node = next(n for n in observation.nodes if n.role == "button" and n.name == "Search" and n.frame == "contentFrame")
            return json.dumps({"thought": "submit the search", "action": "click", "frame": node.frame, "ref": node.ref})

        return json.dumps({"thought": "the member detail page is now showing", "action": "done"})


class SearchFromScratchScript(LLMClient):
    """Like `LookUpMemberScript`, but starts from a blank page and
    issues the initial `navigate` itself, so the resulting transcript
    -- and therefore the artifact `cua.agent.recorder` builds from it --
    is fully self-contained: replaying it later never depends on the
    Surface already happening to be on the right page, exactly the same
    expectation `cua.replay.engine` has of every artifact it's handed.
    """

    def __init__(self, surface: Surface, *, start_url: str, member_id: str = "10001") -> None:
        self._surface = surface
        self._start_url = start_url
        self._member_id = member_id
        self._step = 0

    def complete(self, messages: list[LLMMessage]) -> str:
        self._step += 1

        if self._step == 1:
            return json.dumps({"thought": "go to the search page", "action": "navigate", "value": self._start_url})

        observation = self._surface.observe()

        if self._step == 2:
            node = next(n for n in observation.nodes if n.role == "textbox" and n.frame == "contentFrame")
            return json.dumps(
                {"thought": "type the member id", "action": "type", "frame": node.frame, "ref": node.ref, "value": self._member_id}
            )

        if self._step == 3:
            node = next(n for n in observation.nodes if n.role == "button" and n.name == "Search" and n.frame == "contentFrame")
            return json.dumps({"thought": "submit the search", "action": "click", "frame": node.frame, "ref": node.ref})

        return json.dumps({"thought": "the member detail page is now showing", "action": "done"})
