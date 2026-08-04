"""Bounded agent tool: multi-quarter EPS trend + latest ratios + forward."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
from src.application.use_case.view_ticker_fundamentals_trend_use_case import (
    _DEFAULT_QUARTERS,
    _MAX_QUARTERS,
    ViewTickerFundamentalsTrendRequest,
    ViewTickerFundamentalsTrendResult,
    ViewTickerFundamentalsTrendUseCase,
    clamp_quarters,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_fundamentals_trend.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_fundamentals_trend.v1"

_WARN_CODES = frozenset(
    {
        "EARNINGS_HISTORY_UNAVAILABLE",
        "FUNDAMENTALS_UNAVAILABLE",
        "FORWARD_ESTIMATES_UNAVAILABLE",
        "EARNINGS_WINDOW_SHORT",
    }
)


@dataclass(frozen=True)
class TickerFundamentalsTrendArguments(AgentToolArguments):
    ticker: str
    quarters: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.quarters < 1 or self.quarters > _MAX_QUARTERS:
            raise ValueError(f"quarters must be between 1 and {_MAX_QUARTERS}")


@dataclass(frozen=True)
class EarningsQuarterData:
    year: int
    quarter: int
    period_label: str
    eps_actual: float | None
    eps_estimate: float | None
    eps_surprise_pct: float | None
    yoy_growth_pct: float | None
    beat: bool | None


@dataclass(frozen=True)
class LatestFundamentalsData:
    pe_ratio_ttm: float | None
    pbv: float | None
    roe_ttm: float | None
    net_profit_margin: float | None
    revenue_yoy_growth: float | None
    piotroski_f_score: int | None
    dividend_yield: float | None
    market_cap_idr: int | None


@dataclass(frozen=True)
class ForwardEstimateData:
    forward_eps_1y: float | None
    revenue_forward_1y: float | None
    forward_pe: float | None


@dataclass(frozen=True)
class TickerFundamentalsTrendResultData:
    schema_id: str
    ticker: str
    requested_quarters: int
    quarters: tuple[EarningsQuarterData, ...]
    eps_trend_direction: str
    latest_fundamentals: LatestFundamentalsData | None
    forward: ForwardEstimateData | None


class TickerFundamentalsTrendTool:
    """Project multi-quarter EPS + latest ratios + forward for the agent registry."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_FUNDAMENTALS_TREND,
        description=(
            "Return multi-quarter EPS history (actual/estimate/surprise/YoY), a "
            "descriptive eps_trend_direction (rising/falling/flat/unknown), latest "
            "fundamentals ratios (PE/PBV/ROE/NPM/Piotroski as published), and forward "
            "EPS estimates. Deepens get_ticker_dashboard. Facts only — not a quality "
            "or valuation verdict."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "quarters",
                "Optional number of recent earnings quarters (1-8). Empty defaults to 4.",
            ),
        ),
        required_context="LOCAL_EARNINGS_AND_FUNDAMENTALS_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, use_case: ViewTickerFundamentalsTrendUseCase) -> None:
        self._use_case = use_case

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerFundamentalsTrendArguments:
        if len(ordered_values) != 2:
            raise ValueError("fundamentals trend tool requires exactly two arguments")
        ticker = ordered_values[0].strip().upper()
        quarters = _parse_quarters(ordered_values[1])
        return TickerFundamentalsTrendArguments(ticker=ticker, quarters=quarters)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerFundamentalsTrendArguments):
            raise TypeError("fundamentals trend tool received the wrong argument type")
        ticker = arguments.ticker
        source_reference = f"ticker-fundamentals-trend:{ticker}"
        provenance = AgentToolProvenance(
            source="ticker-fundamentals-trend-cache",
            source_reference=source_reference,
        )
        try:
            result = self._use_case.execute(
                ViewTickerFundamentalsTrendRequest(
                    ticker=ticker,
                    quarters=arguments.quarters,
                )
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_FUNDAMENTALS_TREND_READ_FAILED",
                error_message="Fundamentals/earnings cache could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if result is None:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_FUNDAMENTALS_TREND_UNAVAILABLE",
                error_message="No earnings history, fundamentals, or forward estimates cached",
                provenance=provenance,
                source_reference=source_reference,
            )

        data = _project(result)
        warnings = result.warnings
        has_warn = any(w in _WARN_CODES for w in warnings)
        status = AgentToolExecutionStatus.PARTIAL if has_warn else AgentToolExecutionStatus.SUCCESS
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=status,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=None,
                status=status.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _project(result: ViewTickerFundamentalsTrendResult) -> TickerFundamentalsTrendResultData:
    return TickerFundamentalsTrendResultData(
        schema_id=_RESULT_SCHEMA_ID,
        ticker=result.ticker,
        requested_quarters=result.requested_quarters,
        quarters=tuple(
            EarningsQuarterData(
                year=q.year,
                quarter=q.quarter,
                period_label=q.period_label,
                eps_actual=q.eps_actual,
                eps_estimate=q.eps_estimate,
                eps_surprise_pct=q.eps_surprise_pct,
                yoy_growth_pct=q.yoy_growth_pct,
                beat=q.beat,
            )
            for q in result.quarters
        ),
        eps_trend_direction=result.eps_trend_direction,
        latest_fundamentals=(
            LatestFundamentalsData(
                pe_ratio_ttm=result.latest_fundamentals.pe_ratio_ttm,
                pbv=result.latest_fundamentals.pbv,
                roe_ttm=result.latest_fundamentals.roe_ttm,
                net_profit_margin=result.latest_fundamentals.net_profit_margin,
                revenue_yoy_growth=result.latest_fundamentals.revenue_yoy_growth,
                piotroski_f_score=result.latest_fundamentals.piotroski_f_score,
                dividend_yield=result.latest_fundamentals.dividend_yield,
                market_cap_idr=result.latest_fundamentals.market_cap_idr,
            )
            if result.latest_fundamentals is not None
            else None
        ),
        forward=(
            ForwardEstimateData(
                forward_eps_1y=result.forward.forward_eps_1y,
                revenue_forward_1y=result.forward.revenue_forward_1y,
                forward_pe=result.forward.forward_pe,
            )
            if result.forward is not None
            else None
        ),
    )


def _parse_quarters(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_QUARTERS
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("quarters must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"quarters must be between 1 and {_MAX_QUARTERS}")
    return clamp_quarters(value)
