from types import SimpleNamespace

import pytest

from src.application.dto.accumulation_agent import AgentModelRequest
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


@pytest.mark.parametrize("finish_reason", ["tool_calls", "content_filter", None])
def test_unsafe_or_unknown_finish_reason_is_malformed(finish_reason) -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="answer"), finish_reason=finish_reason)
        ]
    )
    adapter = DeepSeekAgentModel(
        "secret",
        client=SimpleNamespace(chat=SimpleNamespace(completions=_Completions(response))),
    )
    context = build_agent_accumulation_context(make_candidate())
    with pytest.raises(AgentModelMalformedResponseError):
        adapter.generate(AgentModelRequest("policy", "why", context, 500))


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
