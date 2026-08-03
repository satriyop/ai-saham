"""Bounded agent projection of the shared cache-only ticker dashboard."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

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
from src.application.dto.ticker_dashboard import GetTickerDashboardRequest, TickerDashboard
from src.application.services.ticker_dashboard_flow import (
    FOREIGN_FLOW_WINDOWS,
    window_buy_sell_days,
    window_net,
)
from src.application.services.ticker_dashboard_status import CacheStatus
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.shareholding_composition import ShareholdingComposition
from src.domain.value_objects.ticker_notation import TickerNotationSnapshot

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_dashboard.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_dashboard.result.v1"


@dataclass(frozen=True)
class TickerDashboardArguments(AgentToolArguments):
    ticker: str

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")


@dataclass(frozen=True)
class TickerDashboardFreshnessData:
    key: str
    label: str
    status: str
    as_of: date | None
    age_days: int | None


@dataclass(frozen=True)
class TickerDashboardIdentityData:
    status: str | None
    tradeable: bool | None
    listing_board: str | None
    sector: str | None
    sub_sector: str | None
    notation_codes: tuple[str, ...]
    has_uma: bool | None


@dataclass(frozen=True)
class TickerDashboardPriceData:
    as_of: date
    close_idr: str
    change_1d_pct: float | None
    change_5d_pct: float | None
    change_20d_pct: float | None
    high_52w_idr: str | None
    low_52w_idr: str | None
    range_52w_pct: float | None
    volume: int | None
    avg_volume_20d: float | None
    volume_vs_20d: float | None


@dataclass(frozen=True)
class TickerDashboardFundamentalsData:
    pe_ratio_ttm: float | None
    pbv: float | None
    roe_ttm: float | None
    net_profit_margin: float | None
    revenue_yoy_growth: float | None
    piotroski_f_score: int | None
    dividend_yield: float | None
    market_cap_idr: int | None


@dataclass(frozen=True)
class TickerDashboardForwardEstimatesData:
    forward_eps_1y: float | None
    revenue_forward_1y: float | None
    current_price: float | None
    forward_pe: float | None


@dataclass(frozen=True)
class TickerDashboardAnalystData:
    buy_count: int
    hold_count: int
    sell_count: int
    consensus_label: str
    avg_price_target: float | None
    upside_pct: float | None
    last_updated: date | None


@dataclass(frozen=True)
class TickerDashboardEarningsData:
    year: int
    quarter: int
    eps_actual: float | None
    eps_estimate: float | None
    eps_surprise_pct: float | None
    yoy_growth_pct: float | None


@dataclass(frozen=True)
class TickerDashboardOwnershipData:
    report_date: date | None
    institution_pct: float
    individual_pct: float
    top_holder_name: str
    top_holder_pct: float
    total_shares: int | None


@dataclass(frozen=True)
class TickerDashboardBandarData:
    session_date: date
    broker_accdist: str
    today_accdist: str
    five_day_accdist: str
    top1_accdist: str
    top1_percent: float
    accumulation_score: int
    broad_score: int


@dataclass(frozen=True)
class TickerDashboardFlowWindowData:
    sessions: int
    net_value_idr: str | None
    buy_days: int
    sell_days: int


@dataclass(frozen=True)
class TickerDashboardFlowData:
    source: str
    latest_as_of: date
    latest_net_value_idr: str
    latest_net_lot: int
    point_count: int
    windows: tuple[TickerDashboardFlowWindowData, ...]


@dataclass(frozen=True)
class TickerDashboardResultData:
    schema_id: str
    ticker: str
    mode: str
    as_of: date | None
    today: date
    freshness: tuple[TickerDashboardFreshnessData, ...]
    identity: TickerDashboardIdentityData | None
    price: TickerDashboardPriceData | None
    fundamentals: TickerDashboardFundamentalsData | None
    forward_estimates: TickerDashboardForwardEstimatesData | None
    analyst: TickerDashboardAnalystData | None
    earnings: tuple[TickerDashboardEarningsData, ...]
    ownership: TickerDashboardOwnershipData | None
    bandar: TickerDashboardBandarData | None
    foreign_flow: TickerDashboardFlowData | None
    corporate_action_count: int
    corporate_action_status: str
    insider_transaction_count: int
    insider_status: str
    insider_last_known: date | None
    iev_row_count: int
    sentiment_log_count: int
    profile_available: bool
    seasonality_available: bool
    sector_macro_diagnostic_available: bool
    missing_branches: tuple[str, ...]
    stale_branches: tuple[str, ...]
    error_branches: tuple[str, ...]


class TickerDashboardTool:
    """Execute and project the existing cache-only dashboard use case."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_DASHBOARD,
        description="Return a bounded summary of one ticker's existing local dashboard cache.",
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
        ),
        required_context="LOCAL_TICKER_DASHBOARD_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(
        self,
        use_case: GetTickerDashboardUseCase,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._use_case = use_case
        self._today = today

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerDashboardArguments:
        if len(ordered_values) != 1:
            raise ValueError("ticker dashboard tool requires exactly one argument")
        return TickerDashboardArguments(ordered_values[0])

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerDashboardArguments):
            raise TypeError("ticker dashboard tool received the wrong argument type")
        ticker = arguments.ticker
        provenance = AgentToolProvenance(
            source="ticker-dashboard-cache",
            source_reference=f"ticker-dashboard:{ticker}",
        )
        try:
            dashboard = self._use_case.execute(
                GetTickerDashboardRequest(
                    ticker=ticker,
                    brief=False,
                    today=self._today(),
                )
            )
            data, warnings, usable = project_ticker_dashboard_for_agent(dashboard)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="DASHBOARD_READ_FAILED",
                error_message="Ticker dashboard cache could not be read",
                provenance=provenance,
                source_reference=f"ticker-dashboard:{ticker}",
            )
        as_of_reference = dashboard.as_of.isoformat() if dashboard.as_of else "none"
        source_reference = f"ticker-dashboard:{ticker}:{as_of_reference}"
        provenance = AgentToolProvenance(
            source="ticker-dashboard-cache",
            as_of=dashboard.as_of,
            source_reference=source_reference,
        )
        if not usable:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="DASHBOARD_UNAVAILABLE",
                error_message="No cached ticker dashboard data is available",
                provenance=provenance,
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
                as_of=dashboard.as_of,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def project_ticker_dashboard_for_agent(
    dashboard: TickerDashboard,
) -> tuple[TickerDashboardResultData, tuple[str, ...], bool]:
    """Allow-listed cache-only projection shared by the tool and stage context (ADR-066)."""
    freshness = tuple(
        TickerDashboardFreshnessData(
            key=item.key,
            label=item.label,
            status=item.status.value,
            as_of=item.as_of,
            age_days=item.age_days,
        )
        for item in dashboard.freshness
    )
    missing = [
        item.key
        for item in dashboard.freshness
        if item.status in {CacheStatus.MISSING, CacheStatus.EMPTY}
    ]
    stale = [item.key for item in dashboard.freshness if item.status is CacheStatus.STALE]
    errors = [item.key for item in dashboard.freshness if item.status is CacheStatus.ERROR]
    errors.extend(error.key for error in dashboard.panel_errors if error.key not in errors)

    identity = _identity(dashboard.notation)
    price = _price(dashboard)
    fundamentals = _fundamentals(dashboard.fundamentals)
    forward = _forward(dashboard.forward_estimates)
    analyst = _analyst(dashboard.analyst)
    earnings = tuple(_earnings(item) for item in dashboard.earnings[:4])
    ownership = _ownership(dashboard.ownership)
    bandar = _bandar(dashboard.bandar)
    flow = _flow(dashboard)

    optional = {
        "identity": identity,
        "price": price,
        "fundamentals": fundamentals,
        "forward_estimates": forward,
        "analyst": analyst,
        "earnings": earnings,
        "ownership": ownership,
        "bandar": bandar,
        "flow": flow,
        "profile": dashboard.profile,
        "seasonality": dashboard.seasonality,
        "iev": dashboard.iev_rows,
        "sentiment": dashboard.sentiment_logs,
        "sector_macro": dashboard.sector_macro_context_evidence,
    }
    missing.extend(key for key, value in optional.items() if not value and key not in missing)
    missing_branches = tuple(dict.fromkeys(missing))
    stale_branches = tuple(dict.fromkeys(stale))
    error_branches = tuple(dict.fromkeys(errors))
    warnings = tuple(
        [f"Dashboard cache branch unavailable: {key}" for key in missing_branches]
        + [f"Dashboard cache branch stale: {key}" for key in stale_branches]
        + [f"Dashboard cache branch failed: {key}" for key in error_branches]
    )
    usable = any(optional.values()) or any(
        item.status in {CacheStatus.OK, CacheStatus.STALE, CacheStatus.EMPTY}
        for item in dashboard.freshness
    )
    return (
        TickerDashboardResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=dashboard.ticker,
            mode=dashboard.mode,
            as_of=dashboard.as_of,
            today=dashboard.today,
            freshness=freshness,
            identity=identity,
            price=price,
            fundamentals=fundamentals,
            forward_estimates=forward,
            analyst=analyst,
            earnings=earnings,
            ownership=ownership,
            bandar=bandar,
            foreign_flow=flow,
            corporate_action_count=len(dashboard.corp_actions),
            corporate_action_status=dashboard.corp_status.value,
            insider_transaction_count=len(dashboard.insider_txns),
            insider_status=dashboard.insider_status.value,
            insider_last_known=dashboard.insider_last_known,
            iev_row_count=len(dashboard.iev_rows),
            sentiment_log_count=len(dashboard.sentiment_logs),
            profile_available=dashboard.profile is not None,
            seasonality_available=dashboard.seasonality is not None,
            sector_macro_diagnostic_available=(dashboard.sector_macro_context_evidence is not None),
            missing_branches=missing_branches,
            stale_branches=stale_branches,
            error_branches=error_branches,
        ),
        warnings,
        usable,
    )


def _identity(value: object) -> TickerDashboardIdentityData | None:
    if not isinstance(value, TickerNotationSnapshot):
        return None
    return TickerDashboardIdentityData(
        status=value.status,
        tradeable=value.tradeable,
        listing_board=value.listing_board,
        sector=value.sector,
        sub_sector=value.sub_sector,
        notation_codes=tuple(value.codes),
        has_uma=value.has_uma,
    )


def _price(dashboard: TickerDashboard) -> TickerDashboardPriceData | None:
    value = dashboard.price_structure
    if value is None:
        return None
    return TickerDashboardPriceData(
        as_of=value.as_of,
        close_idr=str(value.close),
        change_1d_pct=value.change_1d_pct,
        change_5d_pct=value.change_5d_pct,
        change_20d_pct=value.change_20d_pct,
        high_52w_idr=str(value.high_52w) if value.high_52w is not None else None,
        low_52w_idr=str(value.low_52w) if value.low_52w is not None else None,
        range_52w_pct=value.range_52w_pct,
        volume=value.volume,
        avg_volume_20d=value.avg_volume_20d,
        volume_vs_20d=value.volume_vs_20d,
    )


def _fundamentals(value: object) -> TickerDashboardFundamentalsData | None:
    if not isinstance(value, CompanyFundamentals):
        return None
    projected = TickerDashboardFundamentalsData(
        pe_ratio_ttm=value.pe_ratio_ttm,
        pbv=value.pbv,
        roe_ttm=value.roe_ttm,
        net_profit_margin=value.net_profit_margin,
        revenue_yoy_growth=value.revenue_yoy_growth,
        piotroski_f_score=value.piotroski_f_score,
        dividend_yield=value.dividend_yield,
        market_cap_idr=value.market_cap_idr,
    )
    if all(
        item is None
        for item in (
            projected.pe_ratio_ttm,
            projected.pbv,
            projected.roe_ttm,
            projected.net_profit_margin,
            projected.revenue_yoy_growth,
            projected.piotroski_f_score,
            projected.dividend_yield,
            projected.market_cap_idr,
        )
    ):
        return None
    return projected


def _forward(value: object) -> TickerDashboardForwardEstimatesData | None:
    if not isinstance(value, ForwardEstimates):
        return None
    projected = TickerDashboardForwardEstimatesData(
        forward_eps_1y=value.forward_eps_1y,
        revenue_forward_1y=value.revenue_forward_1y,
        current_price=value.current_price,
        forward_pe=value.forward_pe,
    )
    if all(
        item is None
        for item in (
            projected.forward_eps_1y,
            projected.revenue_forward_1y,
            projected.current_price,
            projected.forward_pe,
        )
    ):
        return None
    return projected


def _analyst(value: object) -> TickerDashboardAnalystData | None:
    if not isinstance(value, AnalystConsensus):
        return None
    return TickerDashboardAnalystData(
        buy_count=value.buy_count,
        hold_count=value.hold_count,
        sell_count=value.sell_count,
        consensus_label=value.consensus_label,
        avg_price_target=value.avg_price_target,
        upside_pct=value.upside_pct,
        last_updated=value.last_updated,
    )


def _earnings(value: EarningsRecord) -> TickerDashboardEarningsData:
    return TickerDashboardEarningsData(
        year=value.year,
        quarter=value.quarter,
        eps_actual=value.eps_actual,
        eps_estimate=value.eps_estimate,
        eps_surprise_pct=value.eps_surprise_pct,
        yoy_growth_pct=value.yoy_growth_pct,
    )


def _ownership(value: object) -> TickerDashboardOwnershipData | None:
    if not isinstance(value, ShareholdingComposition):
        return None
    return TickerDashboardOwnershipData(
        report_date=value.report_date,
        institution_pct=value.institution_pct,
        individual_pct=value.individual_pct,
        top_holder_name=value.top_holder_name,
        top_holder_pct=value.top_holder_pct,
        total_shares=value.total_shares,
    )


def _bandar(value: object) -> TickerDashboardBandarData | None:
    if not isinstance(value, BandarDetectorSnapshot):
        return None
    return TickerDashboardBandarData(
        session_date=value.session_date,
        broker_accdist=value.broker_accdist,
        today_accdist=value.today_accdist,
        five_day_accdist=value.five_day_accdist,
        top1_accdist=value.top1_accdist,
        top1_percent=value.top1_percent,
        accumulation_score=value.accumulation_score,
        broad_score=value.broad_score,
    )


def _flow(dashboard: TickerDashboard) -> TickerDashboardFlowData | None:
    points = list(dashboard.foreign_flow_points)
    if not points or dashboard.foreign_flow_source is None:
        return None
    latest = points[-1]
    return TickerDashboardFlowData(
        source=dashboard.foreign_flow_source,
        latest_as_of=latest.date,
        latest_net_value_idr=str(latest.net_val),
        latest_net_lot=latest.net_lot,
        point_count=len(points),
        windows=tuple(
            TickerDashboardFlowWindowData(
                sessions=sessions,
                net_value_idr=(
                    str(value) if (value := window_net(points, sessions)) is not None else None
                ),
                buy_days=window_buy_sell_days(points, sessions)[0],
                sell_days=window_buy_sell_days(points, sessions)[1],
            )
            for sessions in FOREIGN_FLOW_WINDOWS
        ),
    )
