"""
IHSGTradingSessionCalendarProvider — DQ-002I (P0-corrected).

Builds a `KnownTradingSessionCalendar` (see
`src/domain/services/trading_session_calendar.py`) from the cached IHSG
benchmark candle series via `MarketDataRepository`.

**Known limitation, deliberately fail-closed:** this repository has no
independently authoritative IDX holiday calendar or ingestion-completeness
manifest — only candle presence/absence. An absent candle on a given
weekday is therefore ambiguous: it could be a genuine IDX holiday, a
partial ingestion failure, a quarantined/deleted row, a provider omission,
or any other cache hole. `get_date_range()` bounding the requested window
is a *necessary* precondition but was previously (incorrectly) treated as
*sufficient* proof that every weekday inside the window was accounted for.
It is not: a cache can easily span `[coverage_start, coverage_end]` at its
outer min/max while still having interior gaps that have nothing to do with
holidays.

Corrected behavior: after bounding by `get_date_range`, this provider
additionally requires every Mon-Fri date in `[coverage_start, coverage_end]`
to have a candle. If even one weekday is missing, the interval is treated
as unproven and `None` is returned — the provider never guesses that an
unexplained weekday gap is a holiday. This intentionally limits the
provider to gap-free windows until a real, independently authoritative
session source (a versioned IDX calendar table, or an ingestion
completeness manifest) exists to replace this heuristic.

This provider is the only place session-calendar construction touches
persistence. The resulting `KnownTradingSessionCalendar` is a pure,
immutable snapshot; `AssessSourceAvailabilityUseCase` never queries a
repository itself.

Layer: Infrastructure
Depends on: Domain ports/value objects, `MarketDataRepository` (existing port)
"""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases
from src.domain.ports.market_data_repository import MarketDataRepository

DEFAULT_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


def _weekdays_in_range(start: date, end: date) -> frozenset[date]:
    """Every Mon-Fri calendar date in [start, end] — used only to detect
    unexplained gaps, never to assert that a weekday IS a session."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return frozenset(days)


class IHSGTradingSessionCalendarProvider:
    """Loads a bounded, proven `KnownTradingSessionCalendar` from cached IHSG candles."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        benchmark: BenchmarkTickerAliases = DEFAULT_BENCHMARK_ALIASES,
    ) -> None:
        self._market_repository = market_repository
        self._benchmark = benchmark

    def load(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> KnownTradingSessionCalendar | None:
        if coverage_start > coverage_end:
            return None

        calendar = self._load_for_ticker(self._benchmark.canonical, coverage_start, coverage_end)
        if calendar is None and self._benchmark.legacy:
            calendar = self._load_for_ticker(self._benchmark.legacy, coverage_start, coverage_end)
        return calendar

    def _load_for_ticker(
        self,
        ticker: str,
        coverage_start: date,
        coverage_end: date,
    ) -> KnownTradingSessionCalendar | None:
        cached_range = self._market_repository.get_date_range(ticker)
        if cached_range is None:
            return None  # no data cached at all for this ticker

        cached_min, cached_max = cached_range
        if cached_min > coverage_start or cached_max < coverage_end:
            # Cache does not fully span the requested window — an absent
            # candle inside the window could mean "holiday" or could mean
            # "never fetched"; we cannot tell them apart, so refuse to
            # pretend the sparse set is complete.
            return None

        candles = self._market_repository.get_candles(
            ticker, start_date=coverage_start, end_date=coverage_end
        )
        sessions = frozenset(c.date for c in candles)

        missing_weekdays = _weekdays_in_range(coverage_start, coverage_end) - sessions
        if missing_weekdays:
            # An unexplained weekday gap: this repository has no
            # independently authoritative way to tell "IDX holiday" apart
            # from "data hole" (partial ingestion, quarantined row,
            # provider omission, ...). Fail closed rather than guess.
            return None

        return KnownTradingSessionCalendar(
            sessions=tuple(sorted(sessions)), coverage_start=coverage_start, coverage_end=coverage_end
        )
