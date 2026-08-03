"""Immutable registry and whole-batch validation for agent read tools."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentModelToolCall,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolGapClue,
    AgentToolName,
    AgentToolSideEffect,
    canonical_json_bytes,
)
from src.application.ports.agent_read_tool import AgentReadToolPort

_ALLOWED_SIDE_EFFECTS = frozenset(
    {
        AgentToolSideEffect.NONE,
        AgentToolSideEffect.NETWORK_READ,
        AgentToolSideEffect.LOCAL_READ_ELEVATED,
    }
)

# Heuristic suggestions when the model invents a tool name (ADR-065 gap loop).
_GAP_SUGGESTIONS: tuple[tuple[str, str, str], ...] = (
    ("top_buyer", "get_ticker_broker_flow", "stock-centric top desks + bandar counts"),
    ("top_seller", "get_ticker_broker_flow", "stock-centric top desks + bandar counts"),
    ("ticker_broker", "get_ticker_broker_flow", "stock-centric top desks + bandar counts"),
    ("broker_flow", "get_ticker_broker_flow", "stock-centric top desks + bandar counts"),
    ("named_desk", "get_ticker_broker_flow", "stock-centric top desks + bandar counts"),
    ("broker", "get_broker_desk", "cache-only broker desk projection"),
    ("desk", "get_broker_desk", "cache-only broker desk projection"),
    ("dashboard", "get_ticker_dashboard", "cache-only ticker dashboard"),
    ("ticker", "get_ticker_dashboard", "cache-only ticker dashboard"),
    ("judge", "judge_accumulation_ticker", "canonical single-ticker accumulation judgment"),
    ("accum", "judge_accumulation_ticker", "canonical single-ticker accumulation judgment"),
    ("visible", "get_visible_cockpit_result", "exact visible Judge context"),
    ("web", "web_research", "external research snippets under confirm"),
    ("search", "web_research", "external research snippets under confirm"),
    ("sql", "ro_data_query", "allowlisted read-only local data ask"),
    ("query", "ro_data_query", "allowlisted read-only local data ask"),
    ("data", "ro_data_query", "allowlisted read-only local data ask"),
)


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


@dataclass(frozen=True)
class PreparedAgentToolBatch:
    """Validated calls plus non-executing gap clues for unregistered names."""

    prepared: tuple[PreparedAgentToolCall, ...]
    gaps: tuple[AgentToolGapClue, ...]
    raw_calls: tuple[AgentModelToolCall, ...]


class AgentToolRegistry:
    def __init__(self, tools: tuple[AgentReadToolPort, ...] = ()) -> None:
        by_name: dict[AgentToolName, AgentReadToolPort] = {}
        for tool in tools:
            definition = tool.definition
            if definition.side_effect not in _ALLOWED_SIDE_EFFECTS:
                raise ValueError(
                    f"unsupported agent tool side_effect: {definition.side_effect.value}"
                )
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
        allow_gaps: bool = False,
    ) -> tuple[PreparedAgentToolCall, ...]:
        """L1-compatible prepare: fail closed on unknown names by default."""
        batch = self.prepare_batch_result(calls, max_calls=max_calls, allow_gaps=allow_gaps)
        if batch.gaps and not allow_gaps:
            raise AgentToolValidationError(f"unknown agent tool: {batch.gaps[0].requested_name!r}")
        if not batch.prepared and batch.gaps:
            # All gaps — caller may continue with empty prepared when allow_gaps.
            if allow_gaps:
                return ()
            raise AgentToolValidationError("agent tool batch has no executable calls")
        return batch.prepared

    def prepare_batch_result(
        self,
        calls: tuple[AgentModelToolCall, ...],
        *,
        max_calls: int,
        allow_gaps: bool = True,
    ) -> PreparedAgentToolBatch:
        if not calls or len(calls) > max_calls:
            raise AgentToolValidationError(f"agent tool batch must contain 1-{max_calls} calls")
        call_ids: set[str] = set()
        canonical_calls: set[tuple[AgentToolName, bytes]] = set()
        prepared: list[PreparedAgentToolCall] = []
        gaps: list[AgentToolGapClue] = []
        for call in calls:
            if call.call_id in call_ids:
                raise AgentToolValidationError("duplicate agent tool call id")
            call_ids.add(call.call_id)
            try:
                name = AgentToolName(call.name)
            except ValueError:
                if not allow_gaps:
                    raise AgentToolValidationError(f"unknown agent tool: {call.name!r}") from None
                gaps.append(suggest_tool_gap(call.name, reason="unregistered tool name"))
                continue
            tool = self._by_name.get(name)
            if tool is None:
                if not allow_gaps:
                    raise AgentToolValidationError(f"unregistered agent tool: {name.value}")
                gaps.append(
                    suggest_tool_gap(
                        name.value,
                        reason="tool not enabled in this composition",
                    )
                )
                continue
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
        return PreparedAgentToolBatch(
            prepared=tuple(prepared),
            gaps=tuple(gaps),
            raw_calls=calls,
        )

    @staticmethod
    def execute(
        call: PreparedAgentToolCall,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        result = call.tool.execute(call.call_id, call.arguments, context)
        if not isinstance(result, AgentToolExecutionResult):
            raise AgentToolExecutionContractError("agent tool returned an invalid result type")
        if result.call_id != call.call_id or result.name is not call.name:
            raise AgentToolExecutionContractError("agent tool result identity mismatch")
        expected_side = call.tool.definition.side_effect
        if result.side_effect is not expected_side:
            raise AgentToolExecutionContractError("agent tool result side_effect mismatch")
        if (
            result.data is not None
            and result.data.schema_id != call.tool.definition.result_schema_id
        ):
            raise AgentToolExecutionContractError("agent tool result schema mismatch")
        return result


def suggest_tool_gap(requested_name: str, *, reason: str) -> AgentToolGapClue:
    low = (requested_name or "").strip().lower()
    for needle, suggested, purpose in _GAP_SUGGESTIONS:
        if needle in low:
            return AgentToolGapClue(
                requested_name=requested_name,
                suggested_our_tool=suggested,
                purpose=purpose,
                reason=reason,
            )
    return AgentToolGapClue(
        requested_name=requested_name or "?",
        suggested_our_tool="get_visible_cockpit_result",
        purpose="exact visible Judge context (extend with a named OUR tool)",
        reason=reason,
    )


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
