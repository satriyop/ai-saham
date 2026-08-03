"""Bounded agent projection: ticker foreign net-flow trend (cache-only series)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

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
from src.application.services.ticker_dashboard_flow import window_buy_sell_days, window_net
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryRequest,
    ViewTickerForeignHistoryResult,
)
from src.domain.entities.broker_flow import ForeignFlowPoint

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_foreign_flow.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_foreign_flow.v1"
_DEFAULT_DAYS = 30
_MAX_DAYS = 60
_MAX_POINT_TAIL = 30

_WARN_WINDOW_SHORT = "FOREIGN_WINDOW_SHORT"
_INFO_FLAT = "FLAT_FOREIGN_FLOW"
_WARN_CODES = frozenset({_WARN_WINDOW_SHORT})

_TREND_RISING = "rising"
_TREND_FALLING = "falling"
_TREND_FLAT = "flat"


class _ForeignHistoryUseCase(Protocol):
    def execute(
        self, request: ViewTickerForeignHistoryRequest
    ) -> ViewTickerForeignHistoryResult | None: ...


@dataclass(frozen=True)
class TickerForeignFlowArguments(AgentToolArguments):
    ticker: str
    days: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.days < 1 or self.days > _MAX_DAYS:
            raise ValueError(f"days must be between 1 and {_MAX_DAYS}")


@dataclass(frozen=True)
class TickerForeignFlowPointData:
    date: date
    net_value_idr: str


@dataclass(frozen=True)
class TickerForeignFlowResultData:
    schema_id: str
    ticker: str
    as_of: date
    days: int
    requested_days: int
    resolved_source: str
    cumulative_net_idr: str
    latest_net_idr: str
    net_buy_sessions: int
    active_sessions: int
    trend_direction: str
    points: tuple[TickerForeignFlowPointData, ...]


class TickerForeignFlowTool:
    """Compose cache-only foreign net history into a bounded trend projection."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_FOREIGN_FLOW,
        description=(
            "Return the aggregate foreign net-flow trend for one ticker from local "
            "cache: cumulative/latest net, net-buy session counts, descriptive "
            "rising/falling/flat direction, and a capped recent point tail. "
            "Facts only — not a foreign strength score."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "days",
                "Optional lookback sessions (1-60). Empty string defaults to 30; "
                "values above 60 are capped at 60.",
            ),
        ),
        required_context="LOCAL_FOREIGN_FLOW_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_case: _ForeignHistoryUseCase) -> None:
        self._use_case = use_case

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerForeignFlowArguments:
        if len(ordered_values) != 2:
            raise ValueError("ticker foreign flow tool requires exactly two arguments")
        ticker = ordered_values[0].strip().upper()
        days = _parse_days(ordered_values[1])
        return TickerForeignFlowArguments(ticker=ticker, days=days)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerForeignFlowArguments):
            raise TypeError("ticker foreign flow tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-foreign-flow:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-foreign-flow-cache",
            source_reference=source_reference,
        )
        try:
            result = self._use_case.execute(
                ViewTickerForeignHistoryRequest(
                    ticker=ticker,
                    days=arguments.days,
                    source="auto",
                )
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_FOREIGN_FLOW_READ_FAILED",
                error_message="Foreign flow cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if result is None or not result.points or result.as_of is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_FOREIGN_FLOW_UNAVAILABLE",
                error_message="No cached foreign flow points are available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        points = list(result.points)
        active = len(points)
        cumulative = window_net(points, active)
        buy_days, _sell_days = window_buy_sell_days(points, active)
        latest = points[-1]
        trend = trend_direction_from_series(points)
        tail = points[-_MAX_POINT_TAIL:]
        point_data = tuple(
            TickerForeignFlowPointData(date=p.date, net_value_idr=str(p.net_val)) for p in tail
        )

        notes: list[str] = []
        if active < arguments.days:
            notes.append(_WARN_WINDOW_SHORT)
        if cumulative == Decimal("0") and all(p.net_val == 0 for p in points):
            notes.append(_INFO_FLAT)

        data = TickerForeignFlowResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=result.ticker,
            as_of=result.as_of,
            days=active,
            requested_days=arguments.days,
            resolved_source=result.resolved_source,
            cumulative_net_idr=str(cumulative if cumulative is not None else Decimal("0")),
            latest_net_idr=str(latest.net_val),
            net_buy_sessions=buy_days,
            active_sessions=active,
            trend_direction=trend,
            points=point_data,
        )
        warnings = tuple(notes)
        has_warn = any(code in _WARN_CODES for code in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        as_of_ref = result.as_of.isoformat()
        source_reference = f"ticker-foreign-flow:{ticker}:{as_of_ref}"
        provenance = AgentToolProvenance(
            source="ticker-foreign-flow-cache",
            as_of=result.as_of,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=result.as_of,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def trend_direction_from_series(
    points: list[ForeignFlowPoint] | tuple[ForeignFlowPoint, ...],
) -> str:
    """Descriptive half-window cumulative compare — not a score.

    First half cumulative net vs second half → rising / falling / flat.
    Single-point series is flat. Equal halves are flat.
    """
    series = list(points)
    n = len(series)
    if n < 2:
        return _TREND_FLAT
    mid = n // 2
    first = series[:mid] if mid else series[:1]
    second = series[mid:] if mid else series[-1:]
    first_sum = sum((p.net_val for p in first), Decimal("0"))
    second_sum = sum((p.net_val for p in second), Decimal("0"))
    if second_sum > first_sum:
        return _TREND_RISING
    if second_sum < first_sum:
        return _TREND_FALLING
    return _TREND_FLAT


def _parse_days(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_DAYS
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("days must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"days must be between 1 and {_MAX_DAYS}")
    return min(value, _MAX_DAYS)
