"""Immutable registry and whole-batch validation for agent read tools."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolName,
    AgentToolSideEffect,
    canonical_json_bytes,
)
from src.application.ports.agent_read_tool import AgentReadToolPort


class AgentToolValidationError(ValueError):
    """A model-proposed batch failed before any tool executed."""


class AgentToolExecutionContractError(RuntimeError):
    """A registered tool violated its declared result contract."""


@dataclass(frozen=True)
class PreparedAgentToolCall:
    call_id: str
    name: AgentToolName
    arguments: AgentToolArguments
    tool: AgentReadToolPort


class AgentToolRegistry:
    def __init__(self, tools: tuple[AgentReadToolPort, ...] = ()) -> None:
        by_name: dict[AgentToolName, AgentReadToolPort] = {}
        for tool in tools:
            definition = tool.definition
            if definition.side_effect is not AgentToolSideEffect.NONE:
                raise ValueError("only side-effect-free agent tools may be registered")
            if definition.name in by_name:
                raise ValueError(f"duplicate registered agent tool: {definition.name.value}")
            by_name[definition.name] = tool
        self._tools = tuple(by_name[name] for name in AgentToolName if name in by_name)
        self._by_name = {tool.definition.name: tool for tool in self._tools}

    @property
    def definitions(self) -> tuple[AgentToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools)

    @property
    def empty(self) -> bool:
        return not self._tools

    def prepare_batch(
        self,
        calls: tuple[AgentModelToolCall, ...],
        *,
        max_calls: int,
    ) -> tuple[PreparedAgentToolCall, ...]:
        if not calls or len(calls) > max_calls:
            raise AgentToolValidationError(f"agent tool batch must contain 1-{max_calls} calls")
        call_ids: set[str] = set()
        canonical_calls: set[tuple[AgentToolName, bytes]] = set()
        prepared: list[PreparedAgentToolCall] = []
        for call in calls:
            if call.call_id in call_ids:
                raise AgentToolValidationError("duplicate agent tool call id")
            call_ids.add(call.call_id)
            try:
                name = AgentToolName(call.name)
            except ValueError as exc:
                raise AgentToolValidationError(f"unknown agent tool: {call.name!r}") from exc
            tool = self._by_name.get(name)
            if tool is None:
                raise AgentToolValidationError(f"unregistered agent tool: {name.value}")
            values = _decode_arguments(call.arguments_json, tool.definition)
            try:
                arguments = tool.build_arguments(values)
            except (TypeError, ValueError) as exc:
                raise AgentToolValidationError(
                    f"invalid arguments for agent tool {name.value}"
                ) from exc
            params = getattr(type(arguments), "__dataclass_params__", None)
            if not isinstance(arguments, AgentToolArguments) or params is None or not params.frozen:
                raise AgentToolValidationError("agent tool arguments must be a frozen dataclass")
            try:
                canonical_arguments = canonical_json_bytes(arguments)
            except (TypeError, ValueError) as exc:
                raise AgentToolValidationError(
                    "agent tool arguments contain unsupported values"
                ) from exc
            identity = (name, canonical_arguments)
            if identity in canonical_calls:
                raise AgentToolValidationError("duplicate agent tool call")
            canonical_calls.add(identity)
            prepared.append(PreparedAgentToolCall(call.call_id, name, arguments, tool))
        return tuple(prepared)

    @staticmethod
    def execute(call: PreparedAgentToolCall) -> AgentToolExecutionResult:
        result = call.tool.execute(call.call_id, call.arguments)
        if not isinstance(result, AgentToolExecutionResult):
            raise AgentToolExecutionContractError("agent tool returned an invalid result type")
        if result.call_id != call.call_id or result.name is not call.name:
            raise AgentToolExecutionContractError("agent tool result identity mismatch")
        if result.side_effect is not AgentToolSideEffect.NONE:
            raise AgentToolExecutionContractError("agent tool result is not read-only")
        if (
            result.data is not None
            and result.data.schema_id != call.tool.definition.result_schema_id
        ):
            raise AgentToolExecutionContractError("agent tool result schema mismatch")
        return result


def _decode_arguments(
    arguments_json: str,
    definition: AgentToolDefinition,
) -> tuple[str, ...]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, value in pairs:
            if key in values:
                raise AgentToolValidationError(f"duplicate agent tool argument: {key}")
            values[key] = value
        return values

    try:
        raw = json.loads(arguments_json, object_pairs_hook=reject_duplicates)
    except AgentToolValidationError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise AgentToolValidationError("agent tool arguments must be valid JSON") from exc
    if not isinstance(raw, dict):
        raise AgentToolValidationError("agent tool arguments must be a JSON object")
    expected = tuple(item.name for item in definition.arguments)
    missing = tuple(name for name in expected if name not in raw)
    extra = tuple(name for name in raw if name not in expected)
    if missing or extra:
        raise AgentToolValidationError(
            f"agent tool argument fields mismatch; missing={missing}, extra={extra}"
        )
    ordered: list[str] = []
    for field in definition.arguments:
        value = raw[field.name]
        if not isinstance(value, str):
            raise AgentToolValidationError(f"agent tool argument {field.name!r} must be a string")
        if field.enum_values and value not in field.enum_values:
            raise AgentToolValidationError(
                f"agent tool argument {field.name!r} is outside its enum"
            )
        ordered.append(value)
    return tuple(ordered)
