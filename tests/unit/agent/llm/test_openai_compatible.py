"""cua.agent.llm.openai_compatible.OpenAICompatibleClient: the shared
implementation behind both Groq and NVIDIA NIM adapters, since both
expose an OpenAI-compatible `/chat/completions` endpoint. Exercised
against a FakeHTTPClient -- no real network, no API key.
"""
import pytest

from cua.agent.llm.base import LLMMessage
from cua.agent.llm.openai_compatible import OpenAICompatibleClient
from tests.unit.agent.llm.conftest import FakeHTTPClient

pytestmark = pytest.mark.unit


def test_returns_the_assistant_message_content():
    http = FakeHTTPClient()
    http.script("https://example.test/v1/chat/completions", content="click the Search button")
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="k", model="m", http_client=http)

    reply = client.complete([LLMMessage(role="user", content="what next?")])

    assert reply == "click the Search button"


def test_posts_to_chat_completions_under_the_base_url():
    http = FakeHTTPClient()
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="k", model="m", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["url"] == "https://example.test/v1/chat/completions"


def test_base_url_trailing_slash_is_tolerated():
    http = FakeHTTPClient()
    client = OpenAICompatibleClient(base_url="https://example.test/v1/", api_key="k", model="m", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["url"] == "https://example.test/v1/chat/completions"


def test_sends_the_api_key_as_a_bearer_token():
    http = FakeHTTPClient()
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="secret-key", model="m", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["headers"]["Authorization"] == "Bearer secret-key"


def test_sends_the_configured_model_and_every_message_role_and_content():
    http = FakeHTTPClient()
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="k", model="llama-x", http_client=http)
    messages = [
        LLMMessage(role="system", content="you are an agent"),
        LLMMessage(role="user", content="the goal is X"),
    ]

    client.complete(messages)

    body = http.requests[0]["json"]
    assert body["model"] == "llama-x"
    assert body["messages"] == [
        {"role": "system", "content": "you are an agent"},
        {"role": "user", "content": "the goal is X"},
    ]


def test_sends_a_deterministic_temperature():
    http = FakeHTTPClient()
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="k", model="m", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["json"]["temperature"] == 0


def test_an_http_error_status_propagates_not_swallowed():
    http = FakeHTTPClient()
    http.script("https://example.test/v1/chat/completions", status_code=500)
    client = OpenAICompatibleClient(base_url="https://example.test/v1", api_key="k", model="m", http_client=http)

    with pytest.raises(RuntimeError):
        client.complete([LLMMessage(role="user", content="hi")])
