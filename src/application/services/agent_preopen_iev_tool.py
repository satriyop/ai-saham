"""Bounded agent projection: pre-open indicative equilibrium value (IEV/NCP)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolFreshness,
    AgentToolName,
    AgentToolProvenance,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.preopen_iev.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.preopen_iev.v1"

_INFO_NO_POST_LOCK_MOVE = "NO_POST_LOCK_MOVE"


class _IevSnapshotRow(Protocol):
    ticker: str
    iev: int
    rank: int
    iep: int | None
    is_ncp_locked: int


class _PreopenIevSource(Protocol):
    def get_snapshot(
        self, snapshot_date: date, top_n: int | None = None
    ) -> list[_IevSnapshotRow]: ...

    def ncp_baseline_iev(self, snapshot_date: date) -> dict[str, int]: ...

    def get_snapshot_dates(self) -> list[date]: ...


@dataclass(frozen=True)
class PreopenIevArguments(AgentToolArguments):
    ticker: str
    session_date: date | None

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")


@dataclass(frozen=True)
class PreopenIevResultData:
    schema_id: str
    ticker: str
    session_date: date
    iev: int
    iep: int | None
    rank: int
    is_ncp_locked: bool
    locked_baseline_iev: int | None
    iev_move_since_lock: int | None


class PreopenIevTool:
    """Project one ticker's current pre-open IEV/IEP vs its 08:56 locked baseline."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_PREOPEN_IEV,
        description=(
            "Return one ticker's pre-open indicative equilibrium value (IEV/IEP) for a "
            "trading session: the current cached reading, its rank among that session's "
            "movers, the 08:56 NCP-locked baseline, and how far the current reading has "
            "moved since that lock. Facts only — not a trade action or verdict."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "session_date",
                "Optional ISO trading date (YYYY-MM-DD). Empty string defaults to the "
                "latest cached session.",
            ),
        ),
        required_context="LOCAL_PREOPEN_IEV_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        source: _PreopenIevSource,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._source = source
        self._today = today

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> PreopenIevArguments:
        if len(ordered_values) != 2:
            raise ValueError("preopen iev tool requires exactly two arguments")
        ticker = ordered_values[0].strip().upper()
        session_date = _parse_session_date(ordered_values[1])
        return PreopenIevArguments(ticker=ticker, session_date=session_date)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, PreopenIevArguments):
            raise TypeError("preopen iev tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"preopen-iev:{ticker}"
        provenance = AgentToolProvenance(
            source="preopen-iev-cache",
            source_reference=source_reference,
        )

        requested = arguments.session_date
        if requested is not None and requested > self._today():
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="SESSION_DATE_IN_FUTURE",
                error_message="Requested session_date is in the future; no pre-open data can exist",
                provenance=provenance,
                source_reference=source_reference,
            )

        try:
            session_date = requested or _latest_session_date(self._source)
            if session_date is None:
                return AgentToolExecutionResult.create(
                    call_id=call_id,
                    name=self.definition.name,
                    status=AgentToolExecutionStatus.UNAVAILABLE,
                    data=None,
                    error_code="PREOPEN_IEV_UNAVAILABLE",
                    error_message="No pre-open IEV snapshots are cached for any session",
                    provenance=provenance,
                    source_reference=source_reference,
                )
            rows = self._source.get_snapshot(session_date)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="PREOPEN_IEV_READ_FAILED",
                error_message="Pre-open IEV cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        row = next((r for r in rows if r.ticker == ticker), None)
        source_reference = f"preopen-iev:{ticker}:{session_date.isoformat()}"
        provenance = AgentToolProvenance(
            source="preopen-iev-cache",
            as_of=session_date,
            source_reference=source_reference,
        )
        if row is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="PREOPEN_IEV_UNAVAILABLE",
                error_message="No cached pre-open IEV snapshot for this ticker/session",
                provenance=provenance,
                source_reference=source_reference,
            )

        try:
            baseline_map = self._source.ncp_baseline_iev(session_date)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="PREOPEN_IEV_READ_FAILED",
                error_message="Pre-open IEV locked baseline could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )
        baseline_iev = baseline_map.get(ticker)
        if baseline_iev is None:
            iev_move: int | None = None
            warnings: tuple[str, ...] = (_INFO_NO_POST_LOCK_MOVE,)
        else:
            iev_move = row.iev - baseline_iev
            warnings = ()

        data = PreopenIevResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=ticker,
            session_date=session_date,
            iev=row.iev,
            iep=row.iep,
            rank=row.rank,
            is_ncp_locked=bool(row.is_ncp_locked),
            locked_baseline_iev=baseline_iev,
            iev_move_since_lock=iev_move,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=session_date,
                status=AgentToolExecutionStatus.SUCCESS.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _latest_session_date(source: _PreopenIevSource) -> date | None:
    dates = source.get_snapshot_dates()
    return dates[-1] if dates else None


def _parse_session_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("session_date must be empty or an ISO date (YYYY-MM-DD)") from exc
