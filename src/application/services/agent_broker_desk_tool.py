"""Bounded agent projection of one named cache-only broker desk view."""

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
from src.application.services.broker_desk_from_daily_flow import (
    DeskCalendarDay,
    DeskDayNet,
    DeskTickerNet,
    DeskTickerWindowCell,
)
from src.application.use_case.view_broker_desk_calendar_use_case import (
    ViewBrokerDeskCalendarRequest,
    ViewBrokerDeskCalendarResult,
)
from src.application.use_case.view_broker_desk_flow_use_case import (
    ViewBrokerDeskFlowRequest,
    ViewBrokerDeskFlowResult,
)
from src.application.use_case.view_broker_desk_history_use_case import (
    ViewBrokerDeskHistoryRequest,
    ViewBrokerDeskHistoryResult,
)
from src.application.use_case.view_broker_desk_show_use_case import (
    ViewBrokerDeskShowRequest,
    ViewBrokerDeskShowResult,
)
from src.application.use_case.view_broker_desk_top_matrix_use_case import (
    ViewBrokerDeskTopMatrixRequest,
    ViewBrokerDeskTopMatrixResult,
)
from src.application.use_case.view_broker_desk_top_stocks_use_case import (
    ViewBrokerDeskTopStocksRequest,
    ViewBrokerDeskTopStocksResult,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType

_BROKER_CODE_PATTERN = re.compile(r"[A-Z]{2}")
_ARGUMENT_SCHEMA_ID = "agent_tool.broker_desk.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.broker_desk.result.v1"
_HISTORY_ROW_LIMIT = 40

_VIEW_ENUM = (
    "SHOW",
    "TOP_STOCKS",
    "TOP_MATRIX",
    "FLOW",
    "CALENDAR",
    "HISTORY",
)


class _ShowUseCase(Protocol):
    def execute(self, request: ViewBrokerDeskShowRequest) -> ViewBrokerDeskShowResult | None: ...


class _TopStocksUseCase(Protocol):
    def execute(
        self, request: ViewBrokerDeskTopStocksRequest
    ) -> ViewBrokerDeskTopStocksResult | None: ...


class _TopMatrixUseCase(Protocol):
    def execute(
        self, request: ViewBrokerDeskTopMatrixRequest
    ) -> ViewBrokerDeskTopMatrixResult | None: ...


class _FlowUseCase(Protocol):
    def execute(self, request: ViewBrokerDeskFlowRequest) -> ViewBrokerDeskFlowResult | None: ...


class _CalendarUseCase(Protocol):
    def execute(
        self, request: ViewBrokerDeskCalendarRequest
    ) -> ViewBrokerDeskCalendarResult | None: ...


class _HistoryUseCase(Protocol):
    def execute(
        self, request: ViewBrokerDeskHistoryRequest
    ) -> ViewBrokerDeskHistoryResult | None: ...


@dataclass(frozen=True)
class BrokerDeskArguments(AgentToolArguments):
    broker_code: str
    view: str

    def __post_init__(self) -> None:
        if _BROKER_CODE_PATTERN.fullmatch(self.broker_code) is None:
            raise ValueError("broker_code must be a canonical two-letter IDX code")
        if self.view not in _VIEW_ENUM:
            raise ValueError(f"unsupported broker desk view: {self.view!r}")


@dataclass(frozen=True)
class BrokerDeskTickerNetData:
    ticker: str
    net_value_idr: str
    net_lot: int
    buy_value_idr: str
    sell_value_idr: str
    sessions: int


@dataclass(frozen=True)
class BrokerDeskShowData:
    day_net_value_idr: str
    day_net_lot: int
    day_ticker_count: int
    top_buy_stocks: tuple[BrokerDeskTickerNetData, ...]
    top_sell_stocks: tuple[BrokerDeskTickerNetData, ...]


@dataclass(frozen=True)
class BrokerDeskTopStocksData:
    date: date
    top_buy_stocks: tuple[BrokerDeskTickerNetData, ...]
    top_sell_stocks: tuple[BrokerDeskTickerNetData, ...]


@dataclass(frozen=True)
class BrokerDeskMatrixCellData:
    ticker: str
    window: int
    net_value_idr: str
    sessions_used: int
    avg_buy_price_idr: str | None
    buy_streak: int
    is_partial: bool


@dataclass(frozen=True)
class BrokerDeskMatrixColumnData:
    window: int
    cells: tuple[BrokerDeskMatrixCellData, ...]


@dataclass(frozen=True)
class BrokerDeskTopMatrixData:
    windows: tuple[int, ...]
    columns: tuple[BrokerDeskMatrixColumnData, ...]
    sessions_cached: int
    top_ticker_1s: str | None


@dataclass(frozen=True)
class BrokerDeskDayNetData:
    date: date
    net_value_idr: str
    net_lot: int
    buy_value_idr: str
    sell_value_idr: str
    ticker_count: int


@dataclass(frozen=True)
class BrokerDeskFlowData:
    days: tuple[BrokerDeskDayNetData, ...]


@dataclass(frozen=True)
class BrokerDeskCalendarDayData:
    date: date
    net_value_idr: str
    buy_value_idr: str
    sell_value_idr: str
    top_ticker: str | None
    top_net_idr: str
    ticker_count: int


@dataclass(frozen=True)
class BrokerDeskCalendarData:
    days: tuple[BrokerDeskCalendarDayData, ...]
    sessions_cached: int


@dataclass(frozen=True)
class BrokerDeskHistoryRowData:
    date: date
    ticker: str
    net_value_idr: str
    net_lot: int
    buy_value_idr: str
    sell_value_idr: str


@dataclass(frozen=True)
class BrokerDeskHistoryData:
    pinned_ticker: str | None
    rows: tuple[BrokerDeskHistoryRowData, ...]
    total_row_count: int
    truncated_row_count: int


@dataclass(frozen=True)
class BrokerDeskResultData:
    schema_id: str
    broker_code: str
    broker_name: str
    broker_type: str
    view: str
    as_of: date | None
    scope_note: str
    show: BrokerDeskShowData | None
    top_stocks: BrokerDeskTopStocksData | None
    top_matrix: BrokerDeskTopMatrixData | None
    flow: BrokerDeskFlowData | None
    calendar: BrokerDeskCalendarData | None
    history: BrokerDeskHistoryData | None


@dataclass(frozen=True)
class BrokerDeskUseCases:
    show: _ShowUseCase
    top_stocks: _TopStocksUseCase
    top_matrix: _TopMatrixUseCase
    flow: _FlowUseCase
    calendar: _CalendarUseCase
    history: _HistoryUseCase


class BrokerDeskTool:
    """Execute and project exactly one named ViewBrokerDesk* use case."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_BROKER_DESK,
        description=(
            "Return a bounded summary of one tracked broker desk view from local "
            "broker_daily_flow cache."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "broker_code",
                "Canonical uppercase two-letter IDX broker code, for example YP.",
            ),
            AgentToolArgumentField(
                "view",
                "Exactly one named desk view to read.",
                enum_values=_VIEW_ENUM,
            ),
        ),
        required_context="LOCAL_BROKER_DESK_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_cases: BrokerDeskUseCases) -> None:
        self._use_cases = use_cases

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> BrokerDeskArguments:
        if len(ordered_values) != 2:
            raise ValueError("broker desk tool requires exactly two arguments")
        return BrokerDeskArguments(ordered_values[0], ordered_values[1])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, BrokerDeskArguments):
            raise TypeError("broker desk tool received the wrong argument type")
        code = arguments.broker_code
        view = arguments.view
        source_reference = f"broker-desk:{code}:{view}"
        provenance = AgentToolProvenance(
            source="broker-desk-cache",
            source_reference=source_reference,
        )
        try:
            projected = _execute_view(self._use_cases, code, view)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="BROKER_DESK_READ_FAILED",
                error_message="Broker desk cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )
        if projected is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="BROKER_DESK_UNAVAILABLE",
                error_message="No cached broker desk data is available for this view",
                provenance=provenance,
                source_reference=source_reference,
            )
        data, warnings, as_of = projected
        as_of_reference = as_of.isoformat() if as_of is not None else "none"
        source_reference = f"broker-desk:{code}:{view}:{as_of_reference}"
        provenance = AgentToolProvenance(
            source="broker-desk-cache",
            as_of=as_of,
            source_reference=source_reference,
        )
        status = AgentToolExecutionStatus.PARTIAL if warnings else AgentToolExecutionStatus.SUCCESS
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=as_of,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _execute_view(
    use_cases: BrokerDeskUseCases,
    broker_code: str,
    view: str,
) -> tuple[BrokerDeskResultData, tuple[str, ...], date | None] | None:
    if view == "SHOW":
        result = use_cases.show.execute(ViewBrokerDeskShowRequest(broker_code=broker_code))
        return project_broker_desk_from_result(view, result)

    if view == "TOP_STOCKS":
        result = use_cases.top_stocks.execute(
            ViewBrokerDeskTopStocksRequest(broker_code=broker_code)
        )
        return project_broker_desk_from_result(view, result)

    if view == "TOP_MATRIX":
        result = use_cases.top_matrix.execute(
            ViewBrokerDeskTopMatrixRequest(broker_code=broker_code)
        )
        return project_broker_desk_from_result(view, result)

    if view == "FLOW":
        result = use_cases.flow.execute(ViewBrokerDeskFlowRequest(broker_code=broker_code))
        return project_broker_desk_from_result(view, result)

    if view == "CALENDAR":
        result = use_cases.calendar.execute(ViewBrokerDeskCalendarRequest(broker_code=broker_code))
        return project_broker_desk_from_result(view, result)

    if view == "HISTORY":
        result = use_cases.history.execute(ViewBrokerDeskHistoryRequest(broker_code=broker_code))
        return project_broker_desk_from_result(view, result)

    raise ValueError(f"unsupported broker desk view: {view!r}")


def project_broker_desk_from_result(
    view: str,
    result: object | None,
) -> tuple[BrokerDeskResultData, tuple[str, ...], date | None] | None:
    """Pure allow-listed projection of one desk use-case result (tool + stage context).

    Accepts the real use-case result types or duck-typed test fixtures with the
    same attributes.
    """
    if result is None:
        return None
    if view == "SHOW":
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            result.as_of,
            result.scope_note,
            show=BrokerDeskShowData(
                day_net_value_idr=_money(result.day_net_value),
                day_net_lot=result.day_net_lot,
                day_ticker_count=result.day_ticker_count,
                top_buy_stocks=_ticker_nets(result.top_buy_stocks),
                top_sell_stocks=_ticker_nets(result.top_sell_stocks),
            ),
        )
        return data, (), result.as_of

    if view == "TOP_STOCKS":
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            result.date,
            result.scope_note,
            top_stocks=BrokerDeskTopStocksData(
                date=result.date,
                top_buy_stocks=_ticker_nets(result.top_buy_stocks),
                top_sell_stocks=_ticker_nets(result.top_sell_stocks),
            ),
        )
        return data, (), result.date

    if view == "TOP_MATRIX":
        columns = tuple(
            BrokerDeskMatrixColumnData(
                window=window,
                cells=tuple(_matrix_cell(cell) for cell in result.columns.get(window, ())),
            )
            for window in result.windows
        )
        warnings: list[str] = []
        if any(cell.is_partial for column in columns for cell in column.cells):
            warnings.append("Broker desk matrix includes partial session windows")
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            result.as_of,
            result.scope_note,
            top_matrix=BrokerDeskTopMatrixData(
                windows=result.windows,
                columns=columns,
                sessions_cached=result.sessions_cached,
                top_ticker_1s=result.top_ticker_1s,
            ),
        )
        return data, tuple(warnings), result.as_of

    if view == "FLOW":
        as_of = result.days[-1].date if result.days else None
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            as_of,
            result.scope_note,
            flow=BrokerDeskFlowData(days=tuple(_day_net(day) for day in result.days)),
        )
        return data, (), as_of

    if view == "CALENDAR":
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            result.as_of,
            result.scope_note,
            calendar=BrokerDeskCalendarData(
                days=tuple(_calendar_day(day) for day in result.days),
                sessions_cached=result.sessions_cached,
            ),
        )
        return data, (), result.as_of

    if view == "HISTORY":
        rows, total, truncated, as_of = _history_rows(result.flows)
        hist_warnings: tuple[str, ...] = ()
        if truncated:
            hist_warnings = (
                f"Broker desk history truncated by {_HISTORY_ROW_LIMIT} row display cap",
            )
        data = _base_result(
            result.broker_code,
            result.broker_name,
            result.broker_type,
            view,
            as_of,
            result.scope_note,
            history=BrokerDeskHistoryData(
                pinned_ticker=result.pinned_ticker,
                rows=rows,
                total_row_count=total,
                truncated_row_count=truncated,
            ),
        )
        return data, hist_warnings, as_of

    raise ValueError(f"unsupported broker desk view: {view!r}")


def _base_result(
    broker_code: str,
    broker_name: str,
    broker_type: BrokerType,
    view: str,
    as_of: date | None,
    scope_note: str,
    *,
    show: BrokerDeskShowData | None = None,
    top_stocks: BrokerDeskTopStocksData | None = None,
    top_matrix: BrokerDeskTopMatrixData | None = None,
    flow: BrokerDeskFlowData | None = None,
    calendar: BrokerDeskCalendarData | None = None,
    history: BrokerDeskHistoryData | None = None,
) -> BrokerDeskResultData:
    return BrokerDeskResultData(
        schema_id=_RESULT_SCHEMA_ID,
        broker_code=broker_code,
        broker_name=broker_name,
        broker_type=broker_type.value,
        view=view,
        as_of=as_of,
        scope_note=scope_note,
        show=show,
        top_stocks=top_stocks,
        top_matrix=top_matrix,
        flow=flow,
        calendar=calendar,
        history=history,
    )


def _money(value: Decimal) -> str:
    return str(value)


def _ticker_nets(rows: tuple[DeskTickerNet, ...]) -> tuple[BrokerDeskTickerNetData, ...]:
    return tuple(
        BrokerDeskTickerNetData(
            ticker=row.ticker,
            net_value_idr=_money(row.net_value),
            net_lot=row.net_lot,
            buy_value_idr=_money(row.buy_value),
            sell_value_idr=_money(row.sell_value),
            sessions=row.sessions,
        )
        for row in rows
    )


def _matrix_cell(cell: DeskTickerWindowCell) -> BrokerDeskMatrixCellData:
    return BrokerDeskMatrixCellData(
        ticker=cell.ticker,
        window=cell.window,
        net_value_idr=_money(cell.net_value),
        sessions_used=cell.sessions_used,
        avg_buy_price_idr=(_money(cell.avg_buy_price) if cell.avg_buy_price is not None else None),
        buy_streak=cell.buy_streak,
        is_partial=cell.is_partial,
    )


def _day_net(day: DeskDayNet) -> BrokerDeskDayNetData:
    return BrokerDeskDayNetData(
        date=day.date,
        net_value_idr=_money(day.net_value),
        net_lot=day.net_lot,
        buy_value_idr=_money(day.buy_value),
        sell_value_idr=_money(day.sell_value),
        ticker_count=day.ticker_count,
    )


def _calendar_day(day: DeskCalendarDay) -> BrokerDeskCalendarDayData:
    return BrokerDeskCalendarDayData(
        date=day.date,
        net_value_idr=_money(day.net_value),
        buy_value_idr=_money(day.buy_value),
        sell_value_idr=_money(day.sell_value),
        top_ticker=day.top_ticker,
        top_net_idr=_money(day.top_net),
        ticker_count=day.ticker_count,
    )


def _history_rows(
    flows: tuple[BrokerDailyFlow, ...],
) -> tuple[tuple[BrokerDeskHistoryRowData, ...], int, int, date | None]:
    ordered = sorted(flows, key=lambda flow: (flow.date, flow.ticker), reverse=True)
    total = len(ordered)
    shown = ordered[:_HISTORY_ROW_LIMIT]
    truncated = max(0, total - len(shown))
    rows = tuple(
        BrokerDeskHistoryRowData(
            date=flow.date,
            ticker=flow.ticker.upper(),
            net_value_idr=_money(flow.net_value),
            net_lot=flow.net_lot,
            buy_value_idr=_money(flow.buy_value),
            sell_value_idr=_money(flow.sell_value),
        )
        for flow in shown
    )
    as_of = ordered[0].date if ordered else None
    return rows, total, truncated, as_of
