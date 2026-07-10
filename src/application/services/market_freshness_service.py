"""
Market data cache-freshness policy.

Owns the "last known IDX trading day" lookup and the derived end-of-range
cache tolerance used to decide whether cached candle/broker data is still
current. Depends only on the MarketDataRepository port — no infrastructure
imports, no adapter concerns.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date

from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.trading_calendar import last_weekday


@dataclass(frozen=True)
class BenchmarkTickerAliases:
    """Canonical benchmark ticker plus a legacy alias to check as fallback."""

    canonical: str
    legacy: str | None = None


class MarketFreshnessService:
    """Derive reference trading days and cache tolerance from cached benchmark data."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def last_known_trading_day(self, benchmark: BenchmarkTickerAliases) -> date | None:
        """
        Return the latest date in the benchmark candle cache.

        Stockbit/Yahoo only include actual IDX trading sessions, so this date
        is the last known trading day, correctly excluding weekends and IDX
        public holidays without a calendar heuristic.

        Returns None on first run before benchmark candles have been cached.
        """
        date_range = self._repository.get_date_range(benchmark.canonical)
        if date_range is None and benchmark.legacy:
            # Temporary compatibility while old local databases still contain the
            # legacy benchmark symbol.
            date_range = self._repository.get_date_range(benchmark.legacy)
        return date_range[1] if date_range else None

    def resolve_reference_trading_day(
        self, benchmark: BenchmarkTickerAliases, today: date
    ) -> date:
        """Last known cached trading day, falling back to the last weekday on first run."""
        return self.last_known_trading_day(benchmark) or last_weekday(today)

    def end_tolerance_days(
        self,
        *,
        is_benchmark: bool,
        benchmark: BenchmarkTickerAliases,
        today: date,
    ) -> int:
        """
        How many calendar days old can cached data be and still be considered
        current? Derived from the last known IDX trading day.

        For the benchmark ticker itself, use the weekday fallback directly to
        break the circular dependency (benchmark candles can't use their own
        stale data to decide if they need updating).
        """
        if is_benchmark:
            last_trading = last_weekday(today)
        else:
            last_trading = self.resolve_reference_trading_day(benchmark, today)
        return max(0, (today - last_trading).days)
