"""NVIDIA NIM (https://build.nvidia.com): also OpenAI-compatible, hosted
open-weight models."""
from __future__ import annotations

import httpx

from cua.agent.llm.base import LLMClient
from cua.agent.llm.openai_compatible import OpenAICompatibleClient

_BASE_URL = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"


def build_nvidia_nim_client(
    *, api_key: str, model: str = _DEFAULT_MODEL, http_client: httpx.Client | None = None
) -> LLMClient:
    return OpenAICompatibleClient(base_url=_BASE_URL, api_key=api_key, model=model, http_client=http_client)
