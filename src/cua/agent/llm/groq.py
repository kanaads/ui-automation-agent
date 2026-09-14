"""Groq (https://console.groq.com): free-tier, the recommended default
provider for the live discovery run (README, .env.example)."""
from __future__ import annotations

import httpx

from cua.agent.llm.base import LLMClient
from cua.agent.llm.openai_compatible import OpenAICompatibleClient

_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"


def build_groq_client(*, api_key: str, model: str = _DEFAULT_MODEL, http_client: httpx.Client | None = None) -> LLMClient:
    return OpenAICompatibleClient(base_url=_BASE_URL, api_key=api_key, model=model, http_client=http_client)
