"""Read-only IHSG candle → KnownTradingSessionCalendar for path-label authority.

Contract: ``idx.trading_sessions.ihsg_candle.v1``

Session dates are IHSG benchmark candle dates when the cache date-range fully
spans the requested coverage window. A weekday without an IHSG candle is a
non-session under this contract (holiday / market closed). This is **not**
independent IDX holiday reconstruction and is distinct from the gap-free
availability provider that fails closed on unexplained weekday holes.

Never creates files, tables, indexes, or columns. Opens SQLite with mode=ro.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases
from src.infrastructure.persistence.ihsg_candle_session_calendar import (
    DEFAULT_BENCHMARK_ALIASES,
    load_ihsg_candle_session_calendar,
)
from src.infrastructure.persistence.sqlite_market_data_read_repository import (
    SQLiteMarketDataReadRepository,
)


class SQLiteIHSGTradingSessionCalendarReadRepository:
    """TradingSessionCalendarReadRepository backed by read-only IHSG candles."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        benchmark: BenchmarkTickerAliases = DEFAULT_BENCHMARK_ALIASES,
        market_reader: SQLiteMarketDataReadRepository | None = None,
    ) -> None:
        self._benchmark = benchmark
        self._market = market_reader or SQLiteMarketDataReadRepository(db_path)

    def load_calendar(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> KnownTradingSessionCalendar | None:
        try:
            return load_ihsg_candle_session_calendar(
                self._market,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                benchmark=self._benchmark,
            )
        except FileNotFoundError:
            return None

    def load(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> KnownTradingSessionCalendar | None:
        return self.load_calendar(coverage_start=coverage_start, coverage_end=coverage_end)
