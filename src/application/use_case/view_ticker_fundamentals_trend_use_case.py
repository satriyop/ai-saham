"""EPS history + latest ratios + forward estimates (cache-only, facts only).

Deepens get_ticker_dashboard (latest only) with multi-quarter EarningsRecord
series. Does not invent a quality score; Piotroski is passed through as a
published metric when present on latest fundamentals.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.forward_estimates import ForwardEstimates

_DEFAULT_QUARTERS = 4
_MAX_QUARTERS = 8

_WARN_EARNINGS_MISSING = "EARNINGS_HISTORY_UNAVAILABLE"
_WARN_FUNDAMENTALS_MISSING = "FUNDAMENTALS_UNAVAILABLE"
_WARN_FORWARD_MISSING = "FORWARD_ESTIMATES_UNAVAILABLE"
_WARN_EARNINGS_SHORT = "EARNINGS_WINDOW_SHORT"

_TREND_RISING = "rising"
_TREND_FALLING = "falling"
_TREND_FLAT = "flat"
_TREND_UNKNOWN = "unknown"


class FundamentalsTrendSource(Protocol):
    def get_earnings_history(self, ticker: str, quarters: int) -> list[EarningsRecord]: ...

    def get_fundamentals(self, ticker: str) -> CompanyFundamentals | None: ...

    def get_forward_estimates(self, ticker: str) -> ForwardEstimates | None: ...


@dataclass(frozen=True)
class ViewTickerFundamentalsTrendRequest:
    ticker: str
    quarters: int = _DEFAULT_QUARTERS


@dataclass(frozen=True)
class EarningsQuarterFacts:
    year: int
    quarter: int
    period_label: str
    eps_actual: float | None
    eps_estimate: float | None
    eps_surprise_pct: float | None
    yoy_growth_pct: float | None
    beat: bool | None


@dataclass(frozen=True)
class LatestFundamentalsFacts:
    pe_ratio_ttm: float | None
    pbv: float | None
    roe_ttm: float | None
    net_profit_margin: float | None
    revenue_yoy_growth: float | None
    piotroski_f_score: int | None
    dividend_yield: float | None
    market_cap_idr: int | None


@dataclass(frozen=True)
class ForwardEstimateFacts:
    forward_eps_1y: float | None
    revenue_forward_1y: float | None
    forward_pe: float | None


@dataclass(frozen=True)
class ViewTickerFundamentalsTrendResult:
    ticker: str
    requested_quarters: int
    quarters: tuple[EarningsQuarterFacts, ...]
    eps_trend_direction: str
    latest_fundamentals: LatestFundamentalsFacts | None
    forward: ForwardEstimateFacts | None
    warnings: tuple[str, ...]


def clamp_quarters(value: int) -> int:
    return max(1, min(int(value), _MAX_QUARTERS))


class ViewTickerFundamentalsTrendUseCase:
    """Compose earnings history + latest fundamentals + forward estimates."""

    def __init__(self, source: FundamentalsTrendSource) -> None:
        self._source = source

    def execute(
        self, request: ViewTickerFundamentalsTrendRequest
    ) -> ViewTickerFundamentalsTrendResult | None:
        ticker = request.ticker.upper().strip()
        n = clamp_quarters(request.quarters)
        warnings: list[str] = []

        try:
            raw_earnings = list(self._source.get_earnings_history(ticker, n) or [])
        except Exception:
            raw_earnings = []
        # Provider returns newest first — keep that order for display.
        earnings = tuple(_quarter(r) for r in raw_earnings[:n])
        if not earnings:
            warnings.append(_WARN_EARNINGS_MISSING)
        elif len(earnings) < n:
            warnings.append(_WARN_EARNINGS_SHORT)

        try:
            fund = self._source.get_fundamentals(ticker)
        except Exception:
            fund = None
        latest = _fundamentals(fund) if isinstance(fund, CompanyFundamentals) else None
        if latest is None:
            warnings.append(_WARN_FUNDAMENTALS_MISSING)

        try:
            fwd = self._source.get_forward_estimates(ticker)
        except Exception:
            fwd = None
        forward = _forward(fwd) if isinstance(fwd, ForwardEstimates) else None
        if forward is None:
            warnings.append(_WARN_FORWARD_MISSING)

        if not earnings and latest is None and forward is None:
            return None

        return ViewTickerFundamentalsTrendResult(
            ticker=ticker,
            requested_quarters=n,
            quarters=earnings,
            eps_trend_direction=eps_trend_direction(raw_earnings[:n]),
            latest_fundamentals=latest,
            forward=forward,
            warnings=tuple(dict.fromkeys(warnings)),
        )


def eps_trend_direction(records: list[EarningsRecord] | tuple[EarningsRecord, ...]) -> str:
    """Descriptive half-window compare of eps_actual (newest-first or oldest-first).

    Prefer chronological order for half-window; records may arrive newest-first.
    """
    series = [r.eps_actual for r in records if r.eps_actual is not None]
    if len(series) < 2:
        return _TREND_UNKNOWN
    # If input was newest-first, reverse for time order.
    # Heuristic: if first record is newer year/quarter than last, reverse.
    chrono = list(records)
    if len(chrono) >= 2:
        a, b = chrono[0], chrono[-1]
        if (a.year, a.quarter) > (b.year, b.quarter):
            chrono = list(reversed(chrono))
    vals = [r.eps_actual for r in chrono if r.eps_actual is not None]
    if len(vals) < 2:
        return _TREND_UNKNOWN
    mid = len(vals) // 2
    first = vals[:mid] if mid else vals[:1]
    second = vals[mid:] if mid else vals[-1:]
    first_avg = sum(first) / len(first)
    second_avg = sum(second) / len(second)
    if second_avg > first_avg:
        return _TREND_RISING
    if second_avg < first_avg:
        return _TREND_FALLING
    return _TREND_FLAT


def _quarter(r: EarningsRecord) -> EarningsQuarterFacts:
    return EarningsQuarterFacts(
        year=r.year,
        quarter=r.quarter,
        period_label=r.period_label,
        eps_actual=r.eps_actual,
        eps_estimate=r.eps_estimate,
        eps_surprise_pct=r.eps_surprise_pct,
        yoy_growth_pct=r.yoy_growth_pct,
        beat=r.beat,
    )


def _fundamentals(f: CompanyFundamentals) -> LatestFundamentalsFacts:
    return LatestFundamentalsFacts(
        pe_ratio_ttm=f.pe_ratio_ttm,
        pbv=f.pbv,
        roe_ttm=f.roe_ttm,
        net_profit_margin=f.net_profit_margin,
        revenue_yoy_growth=f.revenue_yoy_growth,
        piotroski_f_score=f.piotroski_f_score,
        dividend_yield=f.dividend_yield,
        market_cap_idr=f.market_cap_idr,
    )


def _forward(f: ForwardEstimates) -> ForwardEstimateFacts:
    return ForwardEstimateFacts(
        forward_eps_1y=f.forward_eps_1y,
        revenue_forward_1y=f.revenue_forward_1y,
        forward_pe=f.forward_pe,
    )
