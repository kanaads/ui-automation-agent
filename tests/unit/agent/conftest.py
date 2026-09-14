"""Shared fakes for cua.agent tests. `FakeLLMClient` is the LLM-side
equivalent of `tests.unit.replay.conftest.ScriptedSurface`: a fixed
queue of raw text replies, consumed one per `complete()` call, with
every call's messages recorded for assertions.
"""
from __future__ import annotations

from cua.agent.llm.base import LLMClient, LLMMessage


class FakeLLMClient(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses -- the loop asked for one turn too many")
        return self._responses.pop(0)
