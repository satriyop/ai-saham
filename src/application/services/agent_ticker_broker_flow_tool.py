"""Bounded agent projection: stock-centric single-session top desks + bandar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
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
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersResult,
)
from src.domain.entities.broker_flow import BrokerTransaction
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_broker_flow.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_broker_flow.v1"
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 10

_WARN_BANDAR_UNAVAILABLE = "BANDAR_SNAPSHOT_UNAVAILABLE"
_WARN_NAMED_TOPS_UNAVAILABLE = "NAMED_TOPS_UNAVAILABLE"
_WARN_TOPS_FALLBACK_EMPTY = "TOPS_FALLBACK_EMPTY"
_INFO_NO_NET_TOPS = "NO_NET_TOPS"
_INFO_NO_ACCUMULATION_SIDE = "NO_ACCUMULATION_SIDE"
_INFO_NO_DISTRIBUTION_SIDE = "NO_DISTRIBUTION_SIDE"

_WARN_CODES = frozenset(
    {
        _WARN_BANDAR_UNAVAILABLE,
        _WARN_NAMED_TOPS_UNAVAILABLE,
        _WARN_TOPS_FALLBACK_EMPTY,
    }
)


class _TopBrokersUseCase(Protocol):
    def execute(
        self, request: ViewTickerTopBrokersRequest
    ) -> ViewTickerTopBrokersResult | None: ...


class _BandarCacheSource(Protocol):
    def get_bandar(self, ticker: str, session_date: date) -> BandarDetectorSnapshot | None: ...


@dataclass(frozen=True)
class TickerBrokerFlowArguments(AgentToolArguments):
    ticker: str
    target_date: date | None
    limit: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")


@dataclass(frozen=True)
class TickerBrokerFlowDeskData:
    broker_code: str
    broker_name: str
    broker_type: str
    side: str
    net_value_idr: str
    net_lot: int
    buy_value_idr: str
    sell_value_idr: str
    avg_buy_price: str
    avg_sell_price: str


@dataclass(frozen=True)
class TickerBrokerFlowBandarData:
    session_date: date
    broker_accdist: str
    today_accdist: str
    five_day_accdist: str
    top1_accdist: str
    top3_accdist: str | None
    top5_accdist: str | None
    top10_accdist: str | None
    total_buyers: int
    total_sellers: int
    number_broker_buysell: int | None
    top1_percent: float


@dataclass(frozen=True)
class TickerBrokerFlowResultData:
    schema_id: str
    ticker: str
    as_of: date
    limit: int
    tops_source: str | None
    tops_scope: str | None
    tops_scope_note: str | None
    top_accumulating: tuple[TickerBrokerFlowDeskData, ...]
    top_distributing: tuple[TickerBrokerFlowDeskData, ...]
    bandar: TickerBrokerFlowBandarData | None


class TickerBrokerFlowTool:
    """Compose cache-only top desks + bandar snapshot for one ticker session."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_BROKER_FLOW,
        description=(
            "Return named top accumulating and distributing desks for one ticker "
            "on a single cached session, with buyer/seller counts and multi-window "
            "bandar consistency labels when available."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "target_date",
                "Optional ISO session date (YYYY-MM-DD). Empty string = latest "
                "cached summary date for the ticker.",
            ),
            AgentToolArgumentField(
                "limit",
                "Optional max desks per side (1-10). Empty string defaults to 10; "
                "values above 10 are capped at 10.",
            ),
        ),
        required_context="LOCAL_TICKER_TOP_BROKERS_AND_BANDAR_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        top_brokers: _TopBrokersUseCase,
        bandar_source: _BandarCacheSource,
    ) -> None:
        self._top_brokers = top_brokers
        self._bandar_source = bandar_source

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerBrokerFlowArguments:
        if len(ordered_values) != 3:
            raise ValueError("ticker broker flow tool requires exactly three arguments")
        ticker_raw, target_raw, limit_raw = ordered_values
        ticker = ticker_raw.strip().upper()
        target_date = _parse_optional_date(target_raw)
        limit = _parse_limit(limit_raw)
        return TickerBrokerFlowArguments(ticker=ticker, target_date=target_date, limit=limit)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerBrokerFlowArguments):
            raise TypeError("ticker broker flow tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-broker-flow:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-broker-flow-cache",
            source_reference=source_reference,
        )
        try:
            tops = self._top_brokers.execute(
                ViewTickerTopBrokersRequest(
                    ticker=ticker,
                    target_date=arguments.target_date,
                    limit=arguments.limit,
                )
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_BROKER_FLOW_READ_FAILED",
                error_message="Ticker top-broker cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        bandar: BandarDetectorSnapshot | None = None
        bandar_session: date | None = None
        if tops is not None:
            bandar_session = tops.date
        elif arguments.target_date is not None:
            bandar_session = arguments.target_date

        if bandar_session is not None:
            try:
                raw_bandar = self._bandar_source.get_bandar(ticker, bandar_session)
            except Exception:
                return AgentToolExecutionResult.create(
                    call_id=call_id,
                    name=self.definition.name,
                    status=AgentToolExecutionStatus.FAILED,
                    data=None,
                    error_code="TICKER_BROKER_FLOW_READ_FAILED",
                    error_message="Bandar detector cache could not be read",
                    provenance=provenance,
                    source_reference=source_reference,
                )
            if isinstance(raw_bandar, BandarDetectorSnapshot):
                bandar = raw_bandar
            elif raw_bandar is not None:
                # Defensive: only accept the domain VO; ignore unknown payloads.
                bandar = None

        if tops is None and bandar is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_BROKER_FLOW_UNAVAILABLE",
                error_message="No cached top-broker or bandar data is available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        notes: list[str] = []
        as_of = tops.date if tops is not None else bandar.session_date  # type: ignore[union-attr]
        tops_source = tops.tops_source if tops is not None else None
        tops_scope = tops.tops_scope if tops is not None else None
        tops_scope_note = tops.tops_scope_note if tops is not None else None

        if tops is None:
            notes.append(_WARN_NAMED_TOPS_UNAVAILABLE)
            buyers: tuple[TickerBrokerFlowDeskData, ...] = ()
            sellers: tuple[TickerBrokerFlowDeskData, ...] = ()
        else:
            buyers = tuple(_desk_row(tx, side="buy") for tx in tops.top_buyers[: arguments.limit])
            sellers = tuple(
                _desk_row(tx, side="sell") for tx in tops.top_sellers[: arguments.limit]
            )
            if not buyers and not sellers:
                if tops_scope == "tracked_brokers":
                    notes.append(_WARN_TOPS_FALLBACK_EMPTY)
                else:
                    notes.append(_INFO_NO_NET_TOPS)
            elif not buyers:
                notes.append(_INFO_NO_ACCUMULATION_SIDE)
            elif not sellers:
                notes.append(_INFO_NO_DISTRIBUTION_SIDE)

        bandar_data: TickerBrokerFlowBandarData | None = None
        if bandar is None:
            notes.append(_WARN_BANDAR_UNAVAILABLE)
        else:
            bandar_data = TickerBrokerFlowBandarData(
                session_date=bandar.session_date,
                broker_accdist=bandar.broker_accdist,
                today_accdist=bandar.today_accdist,
                five_day_accdist=bandar.five_day_accdist,
                top1_accdist=bandar.top1_accdist,
                top3_accdist=bandar.top3_accdist,
                top5_accdist=bandar.top5_accdist,
                top10_accdist=bandar.top10_accdist,
                total_buyers=bandar.total_buyer,
                total_sellers=bandar.total_seller,
                number_broker_buysell=bandar.number_broker_buysell,
                top1_percent=bandar.top1_percent,
            )

        data = TickerBrokerFlowResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=ticker,
            as_of=as_of,
            limit=arguments.limit,
            tops_source=tops_source,
            tops_scope=tops_scope,
            tops_scope_note=tops_scope_note,
            top_accumulating=buyers,
            top_distributing=sellers,
            bandar=bandar_data,
        )
        warnings = tuple(notes)
        has_warn = any(code in _WARN_CODES for code in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        as_of_ref = as_of.isoformat()
        source_reference = f"ticker-broker-flow:{ticker}:{as_of_ref}"
        provenance = AgentToolProvenance(
            source="ticker-broker-flow-cache",
            as_of=as_of,
            source_reference=source_reference,
        )
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


def _desk_row(tx: BrokerTransaction, *, side: str) -> TickerBrokerFlowDeskData:
    return TickerBrokerFlowDeskData(
        broker_code=tx.broker_code,
        broker_name=tx.broker_name,
        broker_type=tx.broker_type.value,
        side=side,
        net_value_idr=str(tx.net_value),
        net_lot=tx.net_lot,
        buy_value_idr=str(tx.buy_value),
        sell_value_idr=str(tx.sell_value),
        avg_buy_price=str(tx.avg_buy_price),
        avg_sell_price=str(tx.avg_sell_price),
    )


def _parse_optional_date(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("target_date must be empty or an ISO date YYYY-MM-DD") from exc


def _parse_limit(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_LIMIT
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("limit must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
    return min(value, _MAX_LIMIT)
