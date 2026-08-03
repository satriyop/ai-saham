"""Bounded agent tool: multi-session desk persistence over raw daily flow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

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
from src.application.services.ticker_desk_flow_history import (
    _DEFAULT_LIMIT,
    _DEFAULT_SESSIONS,
    _MAX_LIMIT,
    _MAX_SESSIONS,
    DeskRotation,
    DeskWindowFacts,
    ForeignLocalSplit,
    TickerDeskFlowHistoryResult,
    TickerDeskFlowHistoryService,
    clamp_limit,
    clamp_sessions,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_desk_flow_history.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_desk_flow_history.v1"

_WARN_CODES = frozenset({"DESK_FLOW_WINDOW_SHORT", "DESK_ROTATION_SKIPPED"})


@dataclass(frozen=True)
class TickerDeskFlowHistoryArguments(AgentToolArguments):
    ticker: str
    sessions: int
    limit: int
    as_of: date | None

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.sessions < 1 or self.sessions > _MAX_SESSIONS:
            raise ValueError(f"sessions must be between 1 and {_MAX_SESSIONS}")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")


@dataclass(frozen=True)
class DeskHistoryWeeklyPointData:
    week: str
    net_value_idr: str


@dataclass(frozen=True)
class DeskHistoryRowData:
    broker_code: str
    broker_name: str
    is_foreign: bool
    cumulative_net_idr: str
    window_sessions: int
    active_sessions: int
    net_buy_sessions: int
    longest_streak: int
    avg_buy_price: str | None
    avg_sell_price: str | None
    weekly_net: tuple[DeskHistoryWeeklyPointData, ...]


@dataclass(frozen=True)
class DeskHistorySplitData:
    foreign_cumulative_net_idr: str
    local_cumulative_net_idr: str
    foreign_desk_count: int
    local_desk_count: int


@dataclass(frozen=True)
class DeskHistoryRotationData:
    recent_sessions: int
    prior_sessions: int
    entering_accumulators: tuple[str, ...]
    leaving_accumulators: tuple[str, ...]
    entering_distributors: tuple[str, ...]
    leaving_distributors: tuple[str, ...]


@dataclass(frozen=True)
class TickerDeskFlowHistoryResultData:
    schema_id: str
    ticker: str
    as_of: date
    window_sessions: int
    requested_sessions: int
    top_accumulating: tuple[DeskHistoryRowData, ...]
    top_distributing: tuple[DeskHistoryRowData, ...]
    rotation: DeskHistoryRotationData | None
    buy_side_split: DeskHistorySplitData
    sell_side_split: DeskHistorySplitData


class TickerDeskFlowHistoryTool:
    """Agent projection of multi-session desk persistence (facts, not score)."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_DESK_FLOW_HISTORY,
        description=(
            "Return top desks that persistently accumulate or distribute one ticker "
            "over a multi-session window (≤60 sessions) from raw broker_daily_flow: "
            "cumulative net, active/net-buy sessions, longest streak, avg prices, "
            "foreign/local split, rotation, and bounded weekly trajectory. "
            "Facts only — not an accumulation quality score. Complements "
            "get_ticker_broker_flow (single session)."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "sessions",
                "Optional trading-session lookback (1-60). Empty defaults to 60.",
            ),
            AgentToolArgumentField(
                "limit",
                "Optional max desks per side (1-10). Empty defaults to 10.",
            ),
            AgentToolArgumentField(
                "as_of",
                "Optional ISO session date (YYYY-MM-DD). Empty = latest cached session. "
                "Never reads flow after this date (PIT).",
            ),
        ),
        required_context="LOCAL_BROKER_DAILY_FLOW_CACHE",
        timeout_ms=5_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, service: TickerDeskFlowHistoryService) -> None:
        self._service = service

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerDeskFlowHistoryArguments:
        if len(ordered_values) != 4:
            raise ValueError("ticker desk flow history tool requires exactly four arguments")
        ticker = ordered_values[0].strip().upper()
        sessions = _parse_int_capped(
            ordered_values[1], default=_DEFAULT_SESSIONS, cap=_MAX_SESSIONS, name="sessions"
        )
        limit = _parse_int_capped(
            ordered_values[2], default=_DEFAULT_LIMIT, cap=_MAX_LIMIT, name="limit"
        )
        as_of = _parse_optional_date(ordered_values[3])
        return TickerDeskFlowHistoryArguments(
            ticker=ticker,
            sessions=clamp_sessions(sessions),
            limit=clamp_limit(limit),
            as_of=as_of,
        )

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerDeskFlowHistoryArguments):
            raise TypeError("ticker desk flow history tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-desk-flow-history:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-desk-flow-history-cache",
            source_reference=source_reference,
        )
        try:
            computed = self._service.compute(
                ticker,
                sessions=arguments.sessions,
                limit=arguments.limit,
                as_of=arguments.as_of,
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_DESK_FLOW_HISTORY_READ_FAILED",
                error_message="Broker daily flow cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if computed is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_DESK_FLOW_HISTORY_UNAVAILABLE",
                error_message="No cached multi-session broker flow is available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        data = _project(computed)
        warnings = computed.warnings
        has_warn = any(w in _WARN_CODES for w in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        source_reference = f"ticker-desk-flow-history:{ticker}:{computed.as_of.isoformat()}"
        provenance = AgentToolProvenance(
            source="ticker-desk-flow-history-cache",
            as_of=computed.as_of,
            source_reference=source_reference,
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=computed.as_of,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _project(result: TickerDeskFlowHistoryResult) -> TickerDeskFlowHistoryResultData:
    return TickerDeskFlowHistoryResultData(
        schema_id=_RESULT_SCHEMA_ID,
        ticker=result.ticker,
        as_of=result.as_of,
        window_sessions=result.window_sessions,
        requested_sessions=result.requested_sessions,
        top_accumulating=tuple(_row(d) for d in result.top_accumulating),
        top_distributing=tuple(_row(d) for d in result.top_distributing),
        rotation=_rotation(result.rotation),
        buy_side_split=_split(result.buy_side_split),
        sell_side_split=_split(result.sell_side_split),
    )


def _row(d: DeskWindowFacts) -> DeskHistoryRowData:
    return DeskHistoryRowData(
        broker_code=d.broker_code,
        broker_name=d.broker_name,
        is_foreign=d.is_foreign,
        cumulative_net_idr=str(d.cumulative_net),
        window_sessions=d.window_sessions,
        active_sessions=d.active_sessions,
        net_buy_sessions=d.net_buy_sessions,
        longest_streak=d.longest_streak,
        avg_buy_price=str(d.avg_buy_price) if d.avg_buy_price is not None else None,
        avg_sell_price=str(d.avg_sell_price) if d.avg_sell_price is not None else None,
        weekly_net=tuple(
            DeskHistoryWeeklyPointData(week=w, net_value_idr=str(n)) for w, n in d.weekly_net
        ),
    )


def _split(s: ForeignLocalSplit) -> DeskHistorySplitData:
    return DeskHistorySplitData(
        foreign_cumulative_net_idr=str(s.foreign_cumulative_net),
        local_cumulative_net_idr=str(s.local_cumulative_net),
        foreign_desk_count=s.foreign_desk_count,
        local_desk_count=s.local_desk_count,
    )


def _rotation(r: DeskRotation | None) -> DeskHistoryRotationData | None:
    if r is None:
        return None
    return DeskHistoryRotationData(
        recent_sessions=r.recent_sessions,
        prior_sessions=r.prior_sessions,
        entering_accumulators=r.entering_accumulators,
        leaving_accumulators=r.leaving_accumulators,
        entering_distributors=r.entering_distributors,
        leaving_distributors=r.leaving_distributors,
    )


def _parse_optional_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must be empty or an ISO date YYYY-MM-DD") from exc


def _parse_int_capped(raw: str, *, default: int, cap: int, name: str) -> int:
    text = raw.strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be between 1 and {cap}")
    return min(value, cap)
