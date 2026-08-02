from dataclasses import dataclass, replace

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentModelResponseKind,
)
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentToolArgumentField,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
)

pytestmark = pytest.mark.agent


@dataclass(frozen=True)
class _Payload:
    schema_id: str = "agent_tool.test.result.v1"
    value: str = "WATCH"


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


def test_tool_result_reference_is_stable_and_envelope_bound() -> None:
    first = AgentToolExecutionResult.create(
        call_id="call-1",
        name=_definition().name,
        status=AgentToolExecutionStatus.SUCCESS,
        data=_Payload(),
        provenance=AgentToolProvenance("test"),
    )
    second = AgentToolExecutionResult.create(
        call_id="call-1",
        name=_definition().name,
        status=AgentToolExecutionStatus.SUCCESS,
        data=_Payload(),
        provenance=AgentToolProvenance("test"),
    )

    assert first.result_reference == second.result_reference
    assert first.result_reference.startswith("sha256:")
    with pytest.raises(ValueError, match="does not match"):
        replace(first, warnings=("changed",))


def test_tool_result_requires_frozen_typed_payload() -> None:
    @dataclass
    class MutablePayload:
        schema_id: str = "mutable"

    with pytest.raises(ValueError, match="frozen typed dataclass"):
        AgentToolExecutionResult.create(
            call_id="call-1",
            name=_definition().name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=MutablePayload(),
            provenance=AgentToolProvenance("test"),
        )


def test_model_response_rejects_contradictory_answer_and_tools() -> None:
    call = AgentModelToolCall("call-1", _definition().name.value, '{"reference":"x"}')
    with pytest.raises(ValueError, match="answer requires text and no tool calls"):
        AgentModelResponse(
            "answer",
            "deepseek",
            "deepseek-v4-flash",
            kind=AgentModelResponseKind.ANSWER,
            tool_calls=(call,),
        )
    with pytest.raises(ValueError, match="requires one or two calls"):
        AgentModelResponse(
            "",
            "deepseek",
            "deepseek-v4-flash",
            kind=AgentModelResponseKind.TOOL_CALLS,
        )


def test_definition_rejects_limits_wider_than_adr() -> None:
    with pytest.raises(ValueError, match="32768"):
        replace(_definition(), max_result_bytes=32 * 1024 + 1)
