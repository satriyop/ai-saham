"""ADR-065 ro_data_query — allowlisted read-only local data ask (confirm)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
_STATEMENT_TIMEOUT_MS = 2_000

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

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

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
        if not self._db_path.is_file():
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
            with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
                conn.execute(f"PRAGMA busy_timeout={_STATEMENT_TIMEOUT_MS}")
                cur = conn.execute(sql, params)
                colnames = tuple(d[0] for d in (cur.description or ()))
                raw_rows = cur.fetchmany(_MAX_ROWS)
        except sqlite3.Error:
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
        rows = tuple(tuple("" if c is None else str(c) for c in row) for row in raw_rows)
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
            columns=colnames,
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
