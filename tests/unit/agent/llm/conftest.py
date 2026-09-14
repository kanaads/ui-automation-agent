"""Fakes for the LLM client layer. No test in this package ever makes a
real network call or needs a real API key/AWS session -- every provider
adapter accepts its transport (an httpx.Client-shaped object for the
OpenAI-compatible providers, a boto3 bedrock-runtime-shaped object for
Bedrock) as a constructor parameter specifically so a fake can stand in
for it here.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _FakeResponse:
    _payload: dict
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeHTTPClient:
    """Stands in for httpx.Client: records every POST it's given and
    returns a scripted response keyed by url."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._responses: dict[str, _FakeResponse] = {}
        self._default_content = "default reply"

    def script(self, url: str, *, content: str | None = None, status_code: int = 200) -> None:
        payload = {"choices": [{"message": {"content": content if content is not None else self._default_content}}]}
        self._responses[url] = _FakeResponse(payload, status_code=status_code)

    def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self._responses.get(url, _FakeResponse({"choices": [{"message": {"content": self._default_content}}]}))


@dataclass
class FakeBedrockRuntime:
    """Stands in for a boto3 bedrock-runtime client's `converse()`."""

    reply_text: str = "default bedrock reply"
    calls: list[dict] = field(default_factory=list)

    def converse(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.reply_text}]}}}
