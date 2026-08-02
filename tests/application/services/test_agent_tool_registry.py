from dataclasses import dataclass

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolProvenance,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_tool_registry import (
    AgentToolExecutionContractError,
    AgentToolRegistry,
    AgentToolValidationError,
)
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
    def __init__(self, name=AgentToolName.GET_VISIBLE_COCKPIT_RESULT) -> None:
        self._definition = AgentToolDefinition(
            name=name,
            description="Return one bounded result.",
            argument_schema_id="agent_tool.test.args.v1",
            result_schema_id="agent_tool.test.result.v1",
            arguments=(AgentToolArgumentField("reference", "Exact result reference."),),
            required_context="VISIBLE_RESULT",
            timeout_ms=100,
            max_result_bytes=4096,
        )
        self.executed: list[str] = []

    @property
    def definition(self):
        return self._definition

    def build_arguments(self, ordered_values):
        return _Args(*ordered_values)

    def execute(self, call_id, arguments, context):
        self.executed.append(arguments.reference)
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=_Payload(self.definition.result_schema_id, arguments.reference),
            provenance=AgentToolProvenance("recording-fake"),
        )


def _call(arguments='{"reference":"sha256:abc"}', *, call_id="call-1", name=None):
    return AgentModelToolCall(
        call_id,
        name or AgentToolName.GET_VISIBLE_COCKPIT_RESULT.value,
        arguments,
    )


def _context():
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


@pytest.mark.parametrize(
    "call",
    [
        _call("not-json"),
        _call("[]"),
        _call("{}"),
        _call('{"reference":"x","extra":"y"}'),
        _call('{"reference":7}'),
        _call('{"reference":"x","reference":"y"}'),
        _call(name="invented_tool"),
        _call(name=AgentToolName.GET_TICKER_DASHBOARD.value),
    ],
)
def test_invalid_batch_is_rejected_before_execution(call) -> None:
    tool = _Tool()
    registry = AgentToolRegistry((tool,))

    with pytest.raises(AgentToolValidationError):
        registry.prepare_batch((call,), max_calls=2)

    assert tool.executed == []


@pytest.mark.parametrize(
    "calls",
    [
        (_call(call_id="same"), _call('{"reference":"other"}', call_id="same")),
        (_call(call_id="one"), _call(call_id="two")),
        (_call(call_id="one"), _call('{"reference":"two"}', call_id="two"), _call()),
    ],
)
def test_duplicate_or_over_count_batch_fails_whole_preflight(calls) -> None:
    tool = _Tool()
    registry = AgentToolRegistry((tool,))

    with pytest.raises(AgentToolValidationError):
        registry.prepare_batch(calls, max_calls=2)

    assert tool.executed == []


def test_registry_is_closed_deterministic_and_executes_typed_arguments() -> None:
    second = _Tool(AgentToolName.GET_TICKER_DASHBOARD)
    first = _Tool()
    registry = AgentToolRegistry((second, first))

    assert tuple(item.name for item in registry.definitions) == (
        AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
        AgentToolName.GET_TICKER_DASHBOARD,
    )
    prepared = registry.prepare_batch((_call(),), max_calls=2)
    result = registry.execute(prepared[0], _context())

    assert first.executed == ["sha256:abc"]
    assert result.status is AgentToolExecutionStatus.SUCCESS


def test_registry_rejects_result_schema_drift() -> None:
    class WrongSchemaTool(_Tool):
        def execute(self, call_id, arguments, context):
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.SUCCESS,
                data=_Payload("agent_tool.wrong.result.v1", arguments.reference),
                provenance=AgentToolProvenance("recording-fake"),
            )

    registry = AgentToolRegistry((WrongSchemaTool(),))
    prepared = registry.prepare_batch((_call(),), max_calls=2)

    with pytest.raises(AgentToolExecutionContractError, match="schema mismatch"):
        registry.execute(prepared[0], _context())
