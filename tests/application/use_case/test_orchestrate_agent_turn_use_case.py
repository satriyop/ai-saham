from dataclasses import dataclass

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentModelResponseKind,
    AgentTurnRequest,
    AgentTurnStatus,
)
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
    AgentToolTurnPolicy,
)
from src.application.services.agent_tool_registry import AgentToolRegistry
from src.application.use_case.orchestrate_agent_turn_use_case import AgentTurnOrchestrator
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


@dataclass(frozen=True)
class _Args(AgentToolArguments):
    reference: str


@dataclass(frozen=True)
class _Payload:
    schema_id: str
    value: str


class _Tool:
    def __init__(self, *, result_status=AgentToolExecutionStatus.SUCCESS, payload_size=5) -> None:
        self._definition = AgentToolDefinition(
            name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
            description="Return an exact visible result.",
            argument_schema_id="agent_tool.test.args.v1",
            result_schema_id="agent_tool.test.result.v1",
            arguments=(AgentToolArgumentField("reference", "Exact result reference."),),
            required_context="VISIBLE_RESULT",
            timeout_ms=100,
            max_result_bytes=1024,
        )
        self.result_status = result_status
        self.payload_size = payload_size
        self.executed: list[str] = []

    @property
    def definition(self):
        return self._definition

    def build_arguments(self, ordered_values):
        return _Args(*ordered_values)

    def execute(self, call_id, arguments):
        self.executed.append(arguments.reference)
        if self.result_status is AgentToolExecutionStatus.SUCCESS:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=self.result_status,
                data=_Payload(self.definition.result_schema_id, "x" * self.payload_size),
                provenance=AgentToolProvenance("recording-fake"),
            )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=self.result_status,
            data=None,
            error_code="UNAVAILABLE",
            error_message="Fixture unavailable",
            provenance=AgentToolProvenance("recording-fake"),
        )


class _Model:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _answer(text="WATCH remains."):
    return AgentModelResponse(text, "deepseek", "deepseek-v4-flash", finish_reason="stop")


def _tool_response(*calls):
    return AgentModelResponse(
        "",
        "deepseek",
        "deepseek-v4-flash",
        finish_reason="tool_calls",
        kind=AgentModelResponseKind.TOOL_CALLS,
        tool_calls=tuple(calls),
    )


def _call(arguments='{"reference":"sha256:abc"}', call_id="call-1"):
    return AgentModelToolCall(
        call_id,
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
        arguments,
    )


def _orchestrator(model, tool=None, *, enabled=True, timed_call=None):
    kwargs = {}
    if timed_call is not None:
        kwargs["timed_call"] = timed_call
    registry = AgentToolRegistry((tool,)) if tool is not None else AgentToolRegistry()
    return AgentTurnOrchestrator(
        model,
        registry,
        AgentToolTurnPolicy(tools_enabled=enabled),
        **kwargs,
    )


def test_empty_registry_preserves_single_call_zero_tool_behavior() -> None:
    model = _Model([_answer()])
    result = _orchestrator(model).execute(AgentTurnRequest("why?", make_candidate()))

    assert result.status is AgentTurnStatus.SUCCESS
    assert len(model.requests) == 1
    assert model.requests[0].tool_choice is AgentModelToolChoice.NONE
    assert model.requests[0].tool_definitions == ()


def test_valid_batch_executes_sequentially_then_forces_final_answer() -> None:
    calls = (_call(call_id="one"), _call('{"reference":"sha256:def"}', "two"))
    model = _Model([_tool_response(*calls), _answer("Grounded answer.")])
    tool = _Tool()

    result = _orchestrator(model, tool).execute(AgentTurnRequest("compare", make_candidate()))

    assert result.status is AgentTurnStatus.SUCCESS
    assert tool.executed == ["sha256:abc", "sha256:def"]
    assert len(model.requests) == 2
    assert model.requests[0].tool_choice is AgentModelToolChoice.AUTO
    assert model.requests[1].tool_choice is AgentModelToolChoice.NONE
    assert model.requests[1].prior_tool_calls == calls
    assert tuple(item.call_id for item in result.tool_results) == ("one", "two")


def test_invalid_batch_executes_nothing_and_does_not_call_provider_again() -> None:
    model = _Model([_tool_response(_call('{"reference":"x","extra":"bad"}'))])
    tool = _Tool()

    result = _orchestrator(model, tool).execute(AgentTurnRequest("why?", make_candidate()))

    assert result.status is AgentTurnStatus.FAILED
    assert tool.executed == []
    assert len(model.requests) == 1


def test_final_tool_proposal_is_rejected_without_third_provider_call() -> None:
    call = _call()
    model = _Model([_tool_response(call), _tool_response(call)])

    result = _orchestrator(model, _Tool()).execute(AgentTurnRequest("why?", make_candidate()))

    assert result.status is AgentTurnStatus.FAILED
    assert len(model.requests) == 2
    assert "after the final call" in result.error_message


def test_unavailable_tool_can_only_produce_partial_final_answer() -> None:
    model = _Model([_tool_response(_call()), _answer()])
    tool = _Tool(result_status=AgentToolExecutionStatus.UNAVAILABLE)

    result = _orchestrator(model, tool).execute(AgentTurnRequest("why?", make_candidate()))

    assert result.status is AgentTurnStatus.PARTIAL
    assert result.tool_results[0].status is AgentToolExecutionStatus.UNAVAILABLE


def test_tool_timeout_becomes_non_retryable_partial_result() -> None:
    invocation = 0

    def timed_call(call, timeout):
        nonlocal invocation
        invocation += 1
        if invocation == 2:
            raise TimeoutError
        return call()

    model = _Model([_tool_response(_call()), _answer()])
    result = _orchestrator(model, _Tool(), timed_call=timed_call).execute(
        AgentTurnRequest("why?", make_candidate())
    )

    assert result.status is AgentTurnStatus.PARTIAL
    assert result.tool_results[0].error_code == "TOOL_TIMEOUT"
    assert result.tool_results[0].retryable is False


def test_cancellation_after_provider_proposal_starts_no_tool() -> None:
    cancelled = False

    class CancellingModel(_Model):
        def generate(self, request):
            nonlocal cancelled
            result = super().generate(request)
            cancelled = True
            return result

    tool = _Tool()
    model = CancellingModel([_tool_response(_call())])
    result = _orchestrator(model, tool).execute(
        AgentTurnRequest("why?", make_candidate()),
        is_cancelled=lambda: cancelled,
    )

    assert result.status is AgentTurnStatus.CANCELLED
    assert tool.executed == []


def test_tool_result_over_declared_limit_stops_before_final_provider_call() -> None:
    model = _Model([_tool_response(_call())])
    tool = _Tool(payload_size=2_000)

    result = _orchestrator(model, tool).execute(AgentTurnRequest("why?", make_candidate()))

    assert result.status is AgentTurnStatus.FAILED
    assert len(model.requests) == 1
    assert "size limit" in result.error_message
