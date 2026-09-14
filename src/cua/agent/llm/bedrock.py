"""AWS Bedrock, via the `converse` API -- one request/response shape
across every model family Bedrock hosts (Anthropic, Meta, Amazon's own,
...), rather than each model's own invoke_model payload. This module
never imports boto3 itself: `runtime_client` is anything shaped like a
boto3 `bedrock-runtime` client (a `.converse(**kwargs) -> dict` in that
same response shape), constructed by whoever actually wants a live
Bedrock client (cua.agent.llm.factory, only on that branch) -- so unit
tests exercise the real request-building/response-parsing logic here
without boto3 installed, an AWS account, or network access.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from cua.agent.llm.base import LLMClient, LLMMessage


class _BedrockRuntime(Protocol):
    def converse(self, **kwargs: Any) -> dict: ...


class BedrockClient(LLMClient):
    def __init__(self, *, model_id: str, runtime_client: _BedrockRuntime) -> None:
        self._model_id = model_id
        self._runtime = runtime_client

    def complete(self, messages: Sequence[LLMMessage]) -> str:
        system_text = "\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": [{"text": m.content}]} for m in messages if m.role != "system"]

        kwargs: dict[str, Any] = {"modelId": self._model_id, "messages": turns}
        if system_text:
            kwargs["system"] = [{"text": system_text}]

        response = self._runtime.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]
