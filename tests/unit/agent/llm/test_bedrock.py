"""cua.agent.llm.bedrock.BedrockClient: uses Bedrock's provider-agnostic
`converse` API (one shape across every model family Bedrock hosts,
Anthropic included) rather than each model's own invoke_model request
schema. Never imports boto3 itself -- it's handed an already-constructed
runtime client (duck-typed: anything with `.converse(**kwargs) -> dict`
in that response shape), so these tests need no AWS credentials, no
network, and not even boto3 installed.
"""
import pytest

from cua.agent.llm.base import LLMMessage
from cua.agent.llm.bedrock import BedrockClient
from tests.unit.agent.llm.conftest import FakeBedrockRuntime

pytestmark = pytest.mark.unit


def test_returns_the_reply_text():
    runtime = FakeBedrockRuntime(reply_text="click the Search button")
    client = BedrockClient(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", runtime_client=runtime)

    reply = client.complete([LLMMessage(role="user", content="what next?")])

    assert reply == "click the Search button"


def test_sends_the_configured_model_id():
    runtime = FakeBedrockRuntime()
    client = BedrockClient(model_id="my-model-id", runtime_client=runtime)

    client.complete([LLMMessage(role="user", content="hi")])

    assert runtime.calls[0]["modelId"] == "my-model-id"


def test_system_messages_go_in_the_dedicated_system_field_not_the_turn_list():
    runtime = FakeBedrockRuntime()
    client = BedrockClient(model_id="m", runtime_client=runtime)

    client.complete([LLMMessage(role="system", content="you are an agent"), LLMMessage(role="user", content="the goal")])

    call = runtime.calls[0]
    assert call["system"] == [{"text": "you are an agent"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "the goal"}]}]


def test_no_system_message_means_no_system_kwarg_at_all():
    runtime = FakeBedrockRuntime()
    client = BedrockClient(model_id="m", runtime_client=runtime)

    client.complete([LLMMessage(role="user", content="hi")])

    assert "system" not in runtime.calls[0]


def test_multiple_system_messages_are_joined():
    runtime = FakeBedrockRuntime()
    client = BedrockClient(model_id="m", runtime_client=runtime)

    client.complete([LLMMessage(role="system", content="rule one"), LLMMessage(role="system", content="rule two")])

    assert runtime.calls[0]["system"] == [{"text": "rule one\nrule two"}]


def test_multi_turn_history_preserves_role_and_order():
    runtime = FakeBedrockRuntime()
    client = BedrockClient(model_id="m", runtime_client=runtime)

    client.complete(
        [
            LLMMessage(role="user", content="turn 1"),
            LLMMessage(role="assistant", content="reply 1"),
            LLMMessage(role="user", content="turn 2"),
        ]
    )

    assert runtime.calls[0]["messages"] == [
        {"role": "user", "content": [{"text": "turn 1"}]},
        {"role": "assistant", "content": [{"text": "reply 1"}]},
        {"role": "user", "content": [{"text": "turn 2"}]},
    ]
