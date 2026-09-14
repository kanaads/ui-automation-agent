"""Turns the .env.example variables into a concrete LLMClient: the one
place `LLM_PROVIDER` gets read. `env` defaults to the real process
environment (`os.environ`) so `cua.agent.cli` can call this with no
arguments in normal use, but every unit test passes a plain dict
instead -- no test here reads or depends on the real environment.

`http_client`/`bedrock_runtime_client` let a caller (again, only tests)
inject a fake transport; in real use they're left `None` and this
module builds a real one per provider -- `boto3` is imported lazily,
right here, only on the `bedrock` branch, so choosing Groq or NVIDIA
NIM never requires it to be installed at all (it's an optional extra,
see pyproject.toml's `[project.optional-dependencies].bedrock`).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from cua.agent.llm.base import LLMClient
from cua.agent.llm.bedrock import BedrockClient
from cua.agent.llm.groq import build_groq_client
from cua.agent.llm.nvidia_nim import build_nvidia_nim_client

_DEFAULT_BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
_DEFAULT_BEDROCK_REGION = "us-east-1"


class LLMConfigError(ValueError):
    """LLM_PROVIDER is unset/unknown, or a required provider-specific
    variable is missing. A caller's configuration bug, not something a
    discovery run could recover from -- raised outright, same spirit as
    `cua.replay.inputs.ReplayInputError`."""


def build_llm_client_from_env(
    env: Mapping[str, str] | None = None,
    *,
    http_client: httpx.Client | None = None,
    bedrock_runtime_client: Any | None = None,
) -> LLMClient:
    env = env if env is not None else os.environ
    provider = env.get("LLM_PROVIDER", "").strip().lower()

    if provider == "groq":
        return build_groq_client(api_key=_require(env, "GROQ_API_KEY"), http_client=http_client)

    if provider == "nvidia_nim":
        return build_nvidia_nim_client(
            api_key=_require(env, "NVIDIA_NIM_API_KEY"),
            model=env.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct"),
            http_client=http_client,
        )

    if provider == "bedrock":
        runtime = bedrock_runtime_client if bedrock_runtime_client is not None else _real_bedrock_runtime(env)
        return BedrockClient(model_id=env.get("BEDROCK_MODEL_ID", _DEFAULT_BEDROCK_MODEL_ID), runtime_client=runtime)

    if not provider:
        raise LLMConfigError("LLM_PROVIDER is not set; expected one of: groq, bedrock, nvidia_nim")
    raise LLMConfigError(f"unknown LLM_PROVIDER '{provider}'; expected one of: groq, bedrock, nvidia_nim")


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise LLMConfigError(f"LLM_PROVIDER='{env.get('LLM_PROVIDER')}' requires {name} to be set")
    return value


def _real_bedrock_runtime(env: Mapping[str, str]) -> Any:
    import boto3  # deliberately lazy -- see module docstring

    return boto3.client("bedrock-runtime", region_name=env.get("AWS_REGION", _DEFAULT_BEDROCK_REGION))
