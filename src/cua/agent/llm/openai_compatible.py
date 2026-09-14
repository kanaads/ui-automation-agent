"""One implementation behind both Groq and NVIDIA NIM (cua.agent.llm
.groq / .nvidia_nim): both expose the same OpenAI-compatible
`POST {base_url}/chat/completions` shape, so there is exactly one place
that builds that request and parses that response, not two copies of
it drifting apart.

`http_client` is anything shaped like `httpx.Client` (a `.post(url, *,
headers, json) -> Response` with `.raise_for_status()` and `.json()`)
-- defaults to a real one, but every unit test injects a fake so no
test here makes a real network call.
"""
from __future__ import annotations

from collections.abc import Sequence

import httpx

from cua.agent.llm.base import LLMClient, LLMMessage


class OpenAICompatibleClient(LLMClient):
    def __init__(self, *, base_url: str, api_key: str, model: str, http_client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._http = http_client if http_client is not None else httpx.Client(timeout=60.0)

    def complete(self, messages: Sequence[LLMMessage]) -> str:
        response = self._http.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": 0,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
