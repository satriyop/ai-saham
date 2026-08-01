"""Build KnownTradingSessionCalendar from IHSG candle presence (challenge path).

Contract: ``idx.trading_sessions.ihsg_candle.v1``

Shared by read-only status loaders and write-side label generation. Not the
gap-free availability provider used for DQ-002I lag checks.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases

DEFAULT_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


class _CandleMarket(Protocol):
    def get_date_range(self, ticker: str) -> tuple[date, date] | None: ...

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Sequence[object]: ...


def load_ihsg_candle_session_calendar(
    market: _CandleMarket,
    *,
    coverage_start: date,
    coverage_end: date,
    benchmark: BenchmarkTickerAliases = DEFAULT_BENCHMARK_ALIASES,
) -> KnownTradingSessionCalendar | None:
    """Return proven IHSG-candle sessions for coverage, or None if unspanned."""
    if coverage_start > coverage_end:
        return None
    for ticker in (benchmark.canonical, benchmark.legacy):
        if not ticker:
            continue
        calendar = _load_for_ticker(market, ticker, coverage_start, coverage_end)
        if calendar is not None:
            return calendar
    return None


def _load_for_ticker(
    market: _CandleMarket,
    ticker: str,
    coverage_start: date,
    coverage_end: date,
) -> KnownTradingSessionCalendar | None:
    cached_range = market.get_date_range(ticker)
    if cached_range is None:
        return None
    cached_min, cached_max = cached_range
    if cached_min > coverage_start or cached_max < coverage_end:
        return None
    candles = market.get_candles(ticker, start_date=coverage_start, end_date=coverage_end)
    sessions = tuple(sorted({getattr(c, "date") for c in candles}))
    return KnownTradingSessionCalendar(
        sessions=sessions,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )
