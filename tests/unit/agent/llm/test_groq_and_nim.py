"""cua.agent.llm.groq / cua.agent.llm.nvidia_nim: thin factories over
OpenAICompatibleClient. Just proves each wires the right base URL and a
sane default model, and that a caller-supplied model overrides the
default -- the actual request-building logic is proven once, generically,
in test_openai_compatible.py.
"""
import pytest

from cua.agent.llm.base import LLMMessage
from cua.agent.llm.groq import build_groq_client
from cua.agent.llm.nvidia_nim import build_nvidia_nim_client
from tests.unit.agent.llm.conftest import FakeHTTPClient

pytestmark = pytest.mark.unit


def test_groq_client_posts_to_the_groq_openai_compatible_endpoint():
    http = FakeHTTPClient()
    client = build_groq_client(api_key="k", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert http.requests[0]["headers"]["Authorization"] == "Bearer k"


def test_groq_client_default_model_can_be_overridden():
    http = FakeHTTPClient()
    client = build_groq_client(api_key="k", model="some-other-model", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["json"]["model"] == "some-other-model"


def test_nvidia_nim_client_posts_to_the_nim_endpoint():
    http = FakeHTTPClient()
    client = build_nvidia_nim_client(api_key="k", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"


def test_nvidia_nim_client_default_model_can_be_overridden():
    http = FakeHTTPClient()
    client = build_nvidia_nim_client(api_key="k", model="some-other-model", http_client=http)

    client.complete([LLMMessage(role="user", content="hi")])

    assert http.requests[0]["json"]["model"] == "some-other-model"
