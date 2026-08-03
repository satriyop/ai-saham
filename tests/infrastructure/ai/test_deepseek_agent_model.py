from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelRequest,
    AgentModelResponseKind,
)
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolArgumentField,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
)
from src.application.ports.agent_model import (
    AgentModelMalformedResponseError,
    AgentModelUnavailableError,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.infrastructure.ai.deepseek_agent_model import DeepSeekAgentModel
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


class _Completions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _definition() -> AgentToolDefinition:
    return AgentToolDefinition(
        name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        description="Return an exact visible result.",
        argument_schema_id="agent_tool.test.args.v1",
        result_schema_id="agent_tool.test.result.v1",
        arguments=(AgentToolArgumentField("reference", "Exact result reference."),),
        required_context="VISIBLE_RESULT",
        timeout_ms=100,
        max_result_bytes=1024,
    )


@dataclass(frozen=True)
class _Payload:
    schema_id: str = "agent_tool.test.result.v1"
    value: str = "WATCH"


def test_deepseek_contract_disables_tools_thinking_and_retries() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="WATCH remains."), finish_reason="stop")
        ],
        model="deepseek-v4-flash",
        id="response-1",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
    )
    completions = _Completions(response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    adapter = DeepSeekAgentModel("secret", client=client)
    context = build_agent_accumulation_context(make_candidate())

    result = adapter.generate(AgentModelRequest("policy", "why", context, 500))

    assert result.provider == "deepseek"
    assert result.input_tokens == 10
    assert completions.kwargs["temperature"] == 0.0
    assert completions.kwargs["tool_choice"] == "none"
    assert completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "tools" not in completions.kwargs


def test_content_filter_finish_reason_is_malformed() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="answer"),
                finish_reason="content_filter",
            )
        ]
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    with pytest.raises(AgentModelMalformedResponseError, match="content filter"):
        adapter.generate(AgentModelRequest("policy", "why", context, 500))


def test_none_finish_reason_with_text_is_accepted() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="WATCH remains."), finish_reason=None)
        ],
        model="deepseek-v4-flash",
        id="response-none",
        usage=None,
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    result = adapter.generate(AgentModelRequest("policy", "why", context, 500))
    assert result.text == "WATCH remains."


def test_list_content_parts_are_joined() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {"type": "text", "text": "Part A."},
                        SimpleNamespace(type="text", text="Part B."),
                    ]
                ),
                finish_reason="stop",
            )
        ],
        model="deepseek-v4-flash",
        id="response-parts",
        usage=None,
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    result = adapter.generate(AgentModelRequest("policy", "why", context, 500))
    assert "Part A." in result.text
    assert "Part B." in result.text


def test_malformed_tools_fall_back_to_text_when_present() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Fallback answer from text.",
                    tool_calls=[],
                ),
                finish_reason="tool_calls",
            )
        ],
        model="deepseek-v4-flash",
        id="response-fallback",
        usage=None,
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    result = adapter.generate(
        AgentModelRequest(
            "policy",
            "why",
            context,
            500,
            tool_definitions=(_definition(),),
            tool_choice=AgentModelToolChoice.AUTO,
        )
    )
    assert result.kind is AgentModelResponseKind.ANSWER
    assert result.text == "Fallback answer from text."


def test_resource_finish_reason_is_unavailable() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="answer"),
                finish_reason="insufficient_system_resource",
            )
        ]
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    with pytest.raises(AgentModelUnavailableError):
        adapter.generate(AgentModelRequest("policy", "why", context, 500))


def test_initial_tool_request_serializes_closed_schema_and_normalizes_calls() -> None:
    raw_call = SimpleNamespace(
        id="call-1",
        type="function",
        function=SimpleNamespace(
            name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
            arguments='{"reference":"sha256:abc"}',
        ),
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=[raw_call]),
                finish_reason="tool_calls",
            )
        ],
        model="deepseek-v4-flash",
        id="response-tools",
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8),
    )
    completions = _Completions(response)
    adapter = DeepSeekAgentModel(
        "secret", client=SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )
    context = build_agent_accumulation_context(make_candidate())

    result = adapter.generate(
        AgentModelRequest(
            "policy",
            "why",
            context,
            500,
            tool_definitions=(_definition(),),
            tool_choice=AgentModelToolChoice.AUTO,
        )
    )

    assert result.kind is AgentModelResponseKind.TOOL_CALLS
    assert result.tool_calls == (
        AgentModelToolCall(
            "call-1",
            AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
            '{"reference":"sha256:abc"}',
        ),
    )
    assert completions.kwargs["tool_choice"] == "auto"
    function = completions.kwargs["tools"][0]["function"]
    assert function["parameters"]["additionalProperties"] is False
    assert "strict" not in function


def test_final_tool_request_preserves_call_and_result_then_disables_tools() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="WATCH remains."),
                finish_reason="stop",
            )
        ],
        model="deepseek-v4-flash",
        id="response-final",
        usage=None,
    )
    completions = _Completions(response)
    adapter = DeepSeekAgentModel(
        "secret", client=SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )
    context = build_agent_accumulation_context(make_candidate())
    call = AgentModelToolCall(
        "call-1",
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
        '{"reference":"sha256:abc"}',
    )
    tool_result = AgentToolExecutionResult.create(
        call_id="call-1",
        name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        status=AgentToolExecutionStatus.SUCCESS,
        data=_Payload(),
        provenance=AgentToolProvenance("test"),
    )

    adapter.generate(
        AgentModelRequest(
            "policy",
            "why",
            context,
            500,
            tool_definitions=(_definition(),),
            tool_choice=AgentModelToolChoice.NONE,
            prior_tool_calls=(call,),
            tool_results=(tool_result,),
        )
    )

    assert completions.kwargs["tool_choice"] == "none"
    assert completions.kwargs["messages"][2]["tool_calls"][0]["id"] == "call-1"
    assert completions.kwargs["messages"][3]["tool_call_id"] == "call-1"
    assert tool_result.result_reference in completions.kwargs["messages"][3]["content"]


@pytest.mark.parametrize(
    "raw_calls",
    [
        [],
        [
            SimpleNamespace(
                id="call-1",
                type="function",
                function=SimpleNamespace(name="", arguments="{}"),
            )
        ],
        [
            SimpleNamespace(
                id="call-1",
                type="custom",
                function=SimpleNamespace(name="x", arguments="{}"),
            )
        ],
    ],
)
def test_malformed_provider_tool_calls_fail_closed(raw_calls) -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="", tool_calls=raw_calls),
                finish_reason="tool_calls",
            )
        ]
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    with pytest.raises(AgentModelMalformedResponseError):
        adapter.generate(
            AgentModelRequest(
                "policy",
                "why",
                context,
                500,
                tool_definitions=(_definition(),),
                tool_choice=AgentModelToolChoice.AUTO,
            )
        )
