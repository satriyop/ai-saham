"""ADR-065 ro_data_query — allowlisted read-only local data ask (confirm)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolApproval,
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolGapClue,
    AgentToolName,
    AgentToolProvenance,
    AgentToolSideEffect,
)

_ARGUMENT_SCHEMA_ID = "agent_tool.ro_data_query.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ro_data_query.result.v1"
_MAX_ROWS = 50

# Closed prepared shapes only (not free SQL).
_SHAPES: dict[str, str] = {
    "TICKER_LATEST_CLOSE": (
        "SELECT date, close FROM candles WHERE ticker = :ticker ORDER BY date DESC LIMIT :limit"
    ),
    "TICKER_RECENT_VOLUME": (
        "SELECT date, volume FROM candles WHERE ticker = :ticker ORDER BY date DESC LIMIT :limit"
    ),
    "BROKER_DAY_NET": (
        "SELECT date, net_value FROM broker_daily_flow "
        "WHERE broker_code = :broker_code ORDER BY date DESC LIMIT :limit"
    ),
}


class _AllowlistedRoQueryResult(Protocol):
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class _AllowlistedRoQuery(Protocol):
    def is_available(self) -> bool: ...

    def execute(self, sql: str, params: dict[str, Any]) -> _AllowlistedRoQueryResult: ...


@dataclass(frozen=True)
class RoDataQueryArguments(AgentToolArguments):
    shape: str
    subject: str

    def __post_init__(self) -> None:
        if self.shape not in _SHAPES:
            raise ValueError(f"shape not allowlisted: {self.shape}")
        if not re.fullmatch(r"[A-Z0-9]{2,8}", self.subject.strip().upper()):
            raise ValueError("subject must be a short uppercase ticker or broker code")


@dataclass(frozen=True)
class RoDataQueryResultData:
    schema_id: str
    shape: str
    subject: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    row_count: int


class RoDataQueryTool:
    """Allowlisted SELECT-only local data ask; never invents free SQL."""

    _definition = AgentToolDefinition(
        name=AgentToolName.RO_DATA_QUERY,
        description=(
            "Allowlisted read-only local data ask (prepared shapes only). "
            "Requires operator confirm. Prefer named OUR tools when available."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "shape",
                "Prepared query shape id.",
                enum_values=tuple(_SHAPES.keys()),
            ),
            AgentToolArgumentField(
                "subject",
                "Ticker or broker code (uppercase).",
            ),
        ),
        required_context="OPERATOR_CONFIRM_LOCAL_RO",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
        side_effect=AgentToolSideEffect.LOCAL_READ_ELEVATED,
        approval=AgentToolApproval.PER_CALL,
    )

    def __init__(self, query: _AllowlistedRoQuery) -> None:
        self._query = query

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> RoDataQueryArguments:
        if len(ordered_values) != 2:
            raise ValueError("ro_data_query requires shape and subject")
        return RoDataQueryArguments(ordered_values[0], ordered_values[1])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, RoDataQueryArguments):
            raise TypeError("ro_data_query received the wrong argument type")
        shape = arguments.shape
        subject = arguments.subject.strip().upper()
        limit = 10
        sql = _SHAPES[shape]
        provenance = AgentToolProvenance(
            source="ro-data-query",
            source_reference=f"ro_data_query:{shape}:{subject}",
        )
        if not self._query.is_available():
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="RO_DATA_DB_MISSING",
                error_message="Local database is not available for RO data ask",
                provenance=provenance,
                side_effect=AgentToolSideEffect.LOCAL_READ_ELEVATED,
            )
        params: dict[str, Any] = {"limit": limit}
        if "ticker" in sql:
            params["ticker"] = subject
        if "broker_code" in sql:
            params["broker_code"] = subject
        try:
            result = self._query.execute(sql, params)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="RO_DATA_QUERY_FAILED",
                error_message="Allowlisted RO query failed safely",
                provenance=provenance,
                side_effect=AgentToolSideEffect.LOCAL_READ_ELEVATED,
            )
        rows = result.rows[:_MAX_ROWS]
        if not rows:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="RO_DATA_EMPTY",
                error_message="Allowlisted RO query returned no rows",
                provenance=provenance,
                side_effect=AgentToolSideEffect.LOCAL_READ_ELEVATED,
            )
        data = RoDataQueryResultData(
            schema_id=_RESULT_SCHEMA_ID,
            shape=shape,
            subject=subject,
            columns=result.columns,
            rows=rows,
            row_count=len(rows),
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=("LOCAL_READ_ELEVATED · allowlisted RO · not Action authority",),
            provenance=provenance,
            side_effect=AgentToolSideEffect.LOCAL_READ_ELEVATED,
        )


def ro_shape_gap(requested: str) -> AgentToolGapClue:
    return AgentToolGapClue(
        requested_name=requested,
        suggested_our_tool="get_ticker_dashboard",
        purpose="named cache dashboard instead of free SQL",
        reason="shape outside ro_data_query allowlist",
    )
