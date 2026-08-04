"""Closed, provider-neutral contracts for read-only agent tools."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Protocol


class AgentToolName(str, Enum):
    GET_VISIBLE_COCKPIT_RESULT = "get_visible_cockpit_result"
    GET_TICKER_DASHBOARD = "get_ticker_dashboard"
    JUDGE_ACCUMULATION_TICKER = "judge_accumulation_ticker"
    GET_BROKER_DESK = "get_broker_desk"
    GET_TICKER_BROKER_FLOW = "get_ticker_broker_flow"
    GET_TICKER_FOREIGN_FLOW = "get_ticker_foreign_flow"
    GET_TICKER_DESK_FLOW_HISTORY = "get_ticker_desk_flow_history"
    GET_TICKER_OWNERSHIP = "get_ticker_ownership"
    GET_TICKER_OWNERSHIP_HISTORY = "get_ticker_ownership_history"
    GET_PREOPEN_IEV = "get_preopen_iev"
    GET_TICKER_CORPORATE_ACTIONS = "get_ticker_corporate_actions"
    GET_TICKER_INSIDER_ACTIVITY = "get_ticker_insider_activity"
    GET_TICKER_SECTOR_CONTEXT = "get_ticker_sector_context"
    GET_TICKER_FUNDAMENTALS_TREND = "get_ticker_fundamentals_trend"
    GET_MARKET_REGIME = "get_market_regime"
    # ADR-065 elevated / external (opt-in flags)
    WEB_RESEARCH = "web_research"
    RO_DATA_QUERY = "ro_data_query"


class AgentToolSideEffect(str, Enum):
    NONE = "NONE"
    NETWORK_READ = "NETWORK_READ"
    LOCAL_READ_ELEVATED = "LOCAL_READ_ELEVATED"


class AgentToolApproval(str, Enum):
    """Confirm policy before execute (ADR-065)."""

    NONE = "NONE"
    PER_CALL = "PER_CALL"


class AgentToolArgumentType(str, Enum):
    STRING = "string"


@dataclass(frozen=True)
class AgentToolArgumentField:
    name: str
    description: str
    value_type: AgentToolArgumentType = AgentToolArgumentType.STRING
    enum_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise ValueError(f"invalid agent tool argument name: {self.name!r}")
        if not self.description.strip():
            raise ValueError("agent tool argument description cannot be empty")
        if self.enum_values and len(set(self.enum_values)) != len(self.enum_values):
            raise ValueError("agent tool argument enum values must be unique")


@dataclass(frozen=True)
class AgentToolDefinition:
    name: AgentToolName
    description: str
    argument_schema_id: str
    result_schema_id: str
    arguments: tuple[AgentToolArgumentField, ...]
    required_context: str
    timeout_ms: int
    max_result_bytes: int
    side_effect: AgentToolSideEffect = AgentToolSideEffect.NONE
    approval: AgentToolApproval = AgentToolApproval.NONE

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("agent tool description cannot be empty")
        if not self.argument_schema_id.strip() or not self.result_schema_id.strip():
            raise ValueError("agent tool schema identifiers cannot be empty")
        if not self.required_context.strip():
            raise ValueError("agent tool required context cannot be empty")
        if self.timeout_ms <= 0 or self.timeout_ms > 15_000:
            raise ValueError("agent tool timeout must be between 1 and 15000 ms")
        if self.max_result_bytes <= 0 or self.max_result_bytes > 32 * 1024:
            raise ValueError("agent tool result limit must be between 1 and 32768 bytes")
        names = tuple(item.name for item in self.arguments)
        if len(names) != len(set(names)):
            raise ValueError("agent tool argument names must be unique")
        if self.side_effect is AgentToolSideEffect.NONE:
            if self.approval is not AgentToolApproval.NONE:
                raise ValueError("side_effect=NONE tools cannot require per-call approval")
        elif self.side_effect in {
            AgentToolSideEffect.NETWORK_READ,
            AgentToolSideEffect.LOCAL_READ_ELEVATED,
        }:
            if self.approval is not AgentToolApproval.PER_CALL:
                raise ValueError("elevated/external tools require PER_CALL approval")
        else:
            raise ValueError(f"unsupported agent tool side_effect: {self.side_effect}")


class AgentToolArguments:
    """Marker base for frozen, tool-specific argument DTOs."""


class AgentToolResultPayload(Protocol):
    schema_id: str


@dataclass(frozen=True)
class AgentToolFreshness:
    as_of: date | None
    status: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("agent tool freshness status cannot be empty")


@dataclass(frozen=True)
class AgentToolProvenance:
    source: str
    as_of: date | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("agent tool provenance source cannot be empty")


class AgentToolExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class _AgentToolResultEnvelope:
    call_id: str
    name: AgentToolName
    status: AgentToolExecutionStatus
    data: AgentToolResultPayload | None
    warnings: tuple[str, ...]
    error_code: str | None
    error_message: str | None
    freshness: AgentToolFreshness | None
    provenance: AgentToolProvenance
    source_reference: str | None
    retryable: bool
    side_effect: AgentToolSideEffect


@dataclass(frozen=True)
class AgentToolExecutionResult:
    call_id: str
    name: AgentToolName
    status: AgentToolExecutionStatus
    data: AgentToolResultPayload | None
    warnings: tuple[str, ...]
    error_code: str | None
    error_message: str | None
    freshness: AgentToolFreshness | None
    provenance: AgentToolProvenance
    source_reference: str | None
    result_reference: str
    retryable: bool = False
    side_effect: AgentToolSideEffect = AgentToolSideEffect.NONE

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("agent tool call id cannot be empty")
        if self.side_effect not in {
            AgentToolSideEffect.NONE,
            AgentToolSideEffect.NETWORK_READ,
            AgentToolSideEffect.LOCAL_READ_ELEVATED,
        }:
            raise ValueError(f"unsupported agent tool result side_effect: {self.side_effect}")
        if self.retryable:
            raise ValueError("agent tool results cannot be retryable")
        if self.status is AgentToolExecutionStatus.SUCCESS:
            if self.data is None or self.error_code is not None or self.error_message is not None:
                raise ValueError("successful agent tool result requires only typed data")
        elif self.status is AgentToolExecutionStatus.PARTIAL:
            if self.data is None or not self.warnings:
                raise ValueError("partial agent tool result requires data and warnings")
        elif self.data is not None or not self.error_code or not self.error_message:
            raise ValueError("failed/unavailable agent tool result requires only a typed error")
        if self.data is not None:
            params = getattr(type(self.data), "__dataclass_params__", None)
            if not is_dataclass(self.data) or params is None or not params.frozen:
                raise ValueError("agent tool result data must be a frozen typed dataclass")
            if not str(getattr(self.data, "schema_id", "")).strip():
                raise ValueError("agent tool result data requires a schema_id")
        expected = canonical_reference(self._envelope())
        if self.result_reference != expected:
            raise ValueError("agent tool result reference does not match its envelope")

    @classmethod
    def create(
        cls,
        *,
        call_id: str,
        name: AgentToolName,
        status: AgentToolExecutionStatus,
        data: AgentToolResultPayload | None,
        warnings: tuple[str, ...] = (),
        error_code: str | None = None,
        error_message: str | None = None,
        freshness: AgentToolFreshness | None = None,
        provenance: AgentToolProvenance,
        source_reference: str | None = None,
        side_effect: AgentToolSideEffect = AgentToolSideEffect.NONE,
    ) -> AgentToolExecutionResult:
        envelope = _AgentToolResultEnvelope(
            call_id=call_id,
            name=name,
            status=status,
            data=data,
            warnings=warnings,
            error_code=error_code,
            error_message=error_message,
            freshness=freshness,
            provenance=provenance,
            source_reference=source_reference,
            retryable=False,
            side_effect=side_effect,
        )
        return cls(
            call_id=call_id,
            name=name,
            status=status,
            data=data,
            warnings=warnings,
            error_code=error_code,
            error_message=error_message,
            freshness=freshness,
            provenance=provenance,
            source_reference=source_reference,
            result_reference=canonical_reference(envelope),
            side_effect=side_effect,
        )

    def canonical_payload(self) -> dict[str, object]:
        payload = canonical_json_value(self._envelope())
        assert isinstance(payload, dict)
        return payload | {"result_reference": self.result_reference}

    def serialized_size(self) -> int:
        return len(canonical_json_bytes(self))

    def _envelope(self) -> _AgentToolResultEnvelope:
        return _AgentToolResultEnvelope(
            call_id=self.call_id,
            name=self.name,
            status=self.status,
            data=self.data,
            warnings=self.warnings,
            error_code=self.error_code,
            error_message=self.error_message,
            freshness=self.freshness,
            provenance=self.provenance,
            source_reference=self.source_reference,
            retryable=self.retryable,
            side_effect=self.side_effect,
        )


@dataclass(frozen=True)
class AgentModelToolCall:
    call_id: str
    name: str
    arguments_json: str

    def __post_init__(self) -> None:
        if not self.call_id.strip() or not self.name.strip() or not self.arguments_json.strip():
            raise ValueError("model tool call fields cannot be empty")


class AgentModelToolChoice(str, Enum):
    AUTO = "auto"
    NONE = "none"


@dataclass(frozen=True)
class AgentToolTurnPolicy:
    """Budgets for one Research Cockpit turn with closed tools.

    L1 (ADR-061): multi_round=False → 2 provider calls, 2 tools, 1 batch.
    L3 (ADR-064): multi_round=True → 3 provider rounds, 4 tools, 2 per batch.
    """

    tools_enabled: bool
    multi_round: bool = False
    max_provider_calls: int = 2
    max_tool_calls: int = 2
    max_tools_per_batch: int = 2
    provider_timeout_seconds: float = 10.0
    tool_budget_seconds: float = 15.0
    turn_deadline_seconds: float = 35.0
    max_total_result_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if self.provider_timeout_seconds != 10.0:
            raise ValueError("provider timeout must be 10 seconds")
        if self.max_total_result_bytes != 64 * 1024:
            raise ValueError("total result limit must be 64 KiB")
        if self.max_tools_per_batch != 2:
            raise ValueError("tools per batch must be 2")
        if self.multi_round:
            if self.max_provider_calls != 3 or self.max_tool_calls != 4:
                raise ValueError("ADR-064 multi-round requires 3 provider rounds and 4 tools")
            if self.tool_budget_seconds != 20.0 or self.turn_deadline_seconds != 45.0:
                raise ValueError("ADR-064 multi-round requires 20s tool / 45s turn budgets")
        else:
            if self.max_provider_calls != 2 or self.max_tool_calls != 2:
                raise ValueError("ADR-061 L1 requires exactly 2 provider calls and 2 tools")
            if self.tool_budget_seconds != 15.0 or self.turn_deadline_seconds != 35.0:
                raise ValueError("ADR-061 L1 tool/turn deadlines must match 15s / 35s")

    @classmethod
    def l1(cls, *, tools_enabled: bool = True) -> AgentToolTurnPolicy:
        return cls(tools_enabled=tools_enabled, multi_round=False)

    @classmethod
    def l3(cls, *, tools_enabled: bool = True) -> AgentToolTurnPolicy:
        return cls(
            tools_enabled=tools_enabled,
            multi_round=True,
            max_provider_calls=3,
            max_tool_calls=4,
            tool_budget_seconds=20.0,
            turn_deadline_seconds=45.0,
        )


@dataclass(frozen=True)
class AgentApprovalRequest:
    """Application-owned confirm request before elevated/external execute (ADR-065)."""

    call_id: str
    tool_name: str
    arg_summary: str
    implication: str
    side_effect: AgentToolSideEffect

    def __post_init__(self) -> None:
        if not self.call_id.strip() or not self.tool_name.strip():
            raise ValueError("approval request requires call_id and tool_name")
        if not self.arg_summary.strip() or not self.implication.strip():
            raise ValueError("approval request requires arg_summary and implication")


@dataclass(frozen=True)
class AgentToolGapClue:
    """Structured clue when the model wants an unregistered / blocked capability."""

    requested_name: str
    suggested_our_tool: str
    purpose: str
    reason: str
    code: str = "TOOL_GAP"

    def operator_line(self) -> str:
        return (
            f"{self.code} · suggested our tool: {self.suggested_our_tool} "
            f"({self.purpose}) · requested {self.requested_name}"
        )


def canonical_json_value(value: object) -> object:
    if is_dataclass(value):
        return {
            item.name: canonical_json_value(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [canonical_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("agent canonical JSON rejects non-finite floats")
        return value
    raise TypeError(f"unsupported agent canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_reference(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()
