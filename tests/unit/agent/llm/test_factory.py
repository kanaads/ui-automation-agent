"""cua.agent.llm.factory.build_llm_client_from_env: turns the .env.example
variables (LLM_PROVIDER + provider-specific keys) into a concrete
LLMClient. Never reads the real process environment or touches the
network/AWS in a test -- a plain dict stands in for `env`, and the
Bedrock branch is exercised via an injected fake runtime client so it
never needs boto3 installed, let alone real AWS credentials.
"""
import sys

import pytest

from cua.agent.llm.bedrock import BedrockClient
from cua.agent.llm.factory import LLMConfigError, build_llm_client_from_env
from cua.agent.llm.openai_compatible import OpenAICompatibleClient
from tests.unit.agent.llm.conftest import FakeBedrockRuntime, FakeHTTPClient

pytestmark = pytest.mark.unit


def test_groq_provider_builds_a_working_client():
    http = FakeHTTPClient()
    client = build_llm_client_from_env({"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gk"}, http_client=http)

    assert isinstance(client, OpenAICompatibleClient)
    from cua.agent.llm.base import LLMMessage

    client.complete([LLMMessage(role="user", content="hi")])
    assert http.requests[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert http.requests[0]["headers"]["Authorization"] == "Bearer gk"


def test_groq_provider_without_an_api_key_raises_a_clear_config_error():
    with pytest.raises(LLMConfigError, match="GROQ_API_KEY"):
        build_llm_client_from_env({"LLM_PROVIDER": "groq"})


def test_nvidia_nim_provider_builds_a_working_client():
    http = FakeHTTPClient()
    client = build_llm_client_from_env(
        {"LLM_PROVIDER": "nvidia_nim", "NVIDIA_NIM_API_KEY": "nk", "NVIDIA_NIM_MODEL": "meta/llama-3.1-70b-instruct"},
        http_client=http,
    )

    from cua.agent.llm.base import LLMMessage

    client.complete([LLMMessage(role="user", content="hi")])
    assert http.requests[0]["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert http.requests[0]["json"]["model"] == "meta/llama-3.1-70b-instruct"


def test_nvidia_nim_provider_without_an_api_key_raises_a_clear_config_error():
    with pytest.raises(LLMConfigError, match="NVIDIA_NIM_API_KEY"):
        build_llm_client_from_env({"LLM_PROVIDER": "nvidia_nim"})


def test_bedrock_provider_builds_a_working_client_via_the_injected_runtime():
    runtime = FakeBedrockRuntime(reply_text="ok")
    client = build_llm_client_from_env(
        {"LLM_PROVIDER": "bedrock", "BEDROCK_MODEL_ID": "my-model", "AWS_REGION": "us-west-2"},
        bedrock_runtime_client=runtime,
    )

    assert isinstance(client, BedrockClient)
    from cua.agent.llm.base import LLMMessage

    assert client.complete([LLMMessage(role="user", content="hi")]) == "ok"
    assert runtime.calls[0]["modelId"] == "my-model"


def test_bedrock_provider_defaults_model_id_when_unset():
    runtime = FakeBedrockRuntime()
    client = build_llm_client_from_env({"LLM_PROVIDER": "bedrock"}, bedrock_runtime_client=runtime)

    from cua.agent.llm.base import LLMMessage

    client.complete([LLMMessage(role="user", content="hi")])
    assert runtime.calls[0]["modelId"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_bedrock_provider_with_no_injected_runtime_builds_a_real_one_via_boto3(monkeypatch):
    """The one branch none of the tests above exercise: no
    `bedrock_runtime_client` was injected, so `build_llm_client_from_env`
    must fall back to `_real_bedrock_runtime`, which lazily imports boto3
    itself. A fake `boto3` module in `sys.modules` proves that branch runs
    -- and runs correctly -- without the real package installed."""

    calls: list[tuple[str, str]] = []

    class _FakeBoto3Module:
        @staticmethod
        def client(service_name: str, *, region_name: str) -> FakeBedrockRuntime:
            calls.append((service_name, region_name))
            return FakeBedrockRuntime(reply_text="from a real-ish boto3 client")

    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3Module())

    client = build_llm_client_from_env({"LLM_PROVIDER": "bedrock", "AWS_REGION": "eu-west-1"})

    assert isinstance(client, BedrockClient)
    assert calls == [("bedrock-runtime", "eu-west-1")]

    from cua.agent.llm.base import LLMMessage

    assert client.complete([LLMMessage(role="user", content="hi")]) == "from a real-ish boto3 client"


def test_bedrock_provider_region_defaults_when_unset(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _FakeBoto3Module:
        @staticmethod
        def client(service_name: str, *, region_name: str) -> FakeBedrockRuntime:
            calls.append((service_name, region_name))
            return FakeBedrockRuntime()

    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3Module())

    build_llm_client_from_env({"LLM_PROVIDER": "bedrock"})

    assert calls == [("bedrock-runtime", "us-east-1")]


def test_unknown_provider_raises_a_clear_config_error():
    with pytest.raises(LLMConfigError, match="unknown"):
        build_llm_client_from_env({"LLM_PROVIDER": "some_made_up_provider"})


def test_unset_provider_raises_a_clear_config_error():
    with pytest.raises(LLMConfigError):
        build_llm_client_from_env({})


def test_provider_name_is_case_insensitive():
    http = FakeHTTPClient()
    client = build_llm_client_from_env({"LLM_PROVIDER": "GROQ", "GROQ_API_KEY": "gk"}, http_client=http)

    assert isinstance(client, OpenAICompatibleClient)
