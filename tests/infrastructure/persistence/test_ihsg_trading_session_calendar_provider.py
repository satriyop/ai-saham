"""Tests for IHSGTradingSessionCalendarProvider — DQ-002I."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


def _candle(ticker: str, on: date, close: int = 100) -> Candle:
    return Candle(
        ticker=ticker, date=on, open=close, high=close, low=close, close=close, volume=1000
    )


class FakeMarketRepository(MarketDataRepository):
    """In-memory fake allowing duplicate-date rows to be injected directly
    (impossible via real SQLite's (ticker, date) primary key), to prove the
    provider's own dedup behavior rather than the storage layer's."""

    def __init__(self, candles: dict[str, list[Candle]]) -> None:
        self._candles = candles

    def save_candles(self, candles):
        raise NotImplementedError

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = self._candles.get(ticker, [])
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return rows

    def has_data(self, ticker, start_date, end_date):
        raise NotImplementedError

    def get_date_range(self, ticker):
        rows = self._candles.get(ticker, [])
        if not rows:
            return None
        dates = [c.date for c in rows]
        return min(dates), max(dates)


class TestBoundedQuery:
    def test_query_is_bounded_by_coverage_start_and_end(self, tmp_path: Path):
        """A gap-free Mon-Fri work week (2026-07-13..2026-07-17): every
        weekday inside coverage has a candle, so the provider can prove
        completeness and succeed; markers before/after coverage prove the
        query itself is bounded."""
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles(
            [
                _candle("IHSG", date(2026, 7, 10)),  # before coverage_start
                _candle("IHSG", date(2026, 7, 13)),  # Mon
                _candle("IHSG", date(2026, 7, 14)),  # Tue
                _candle("IHSG", date(2026, 7, 15)),  # Wed
                _candle("IHSG", date(2026, 7, 16)),  # Thu
                _candle("IHSG", date(2026, 7, 17)),  # Fri
                _candle("IHSG", date(2026, 7, 20)),  # after coverage_end
            ]
        )
        provider = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 13), coverage_end=date(2026, 7, 17))

        assert calendar is not None
        assert calendar.sessions == (
            date(2026, 7, 13),
            date(2026, 7, 14),
            date(2026, 7, 15),
            date(2026, 7, 16),
            date(2026, 7, 17),
        )

    def test_future_ihsg_candle_is_excluded(self, tmp_path: Path):
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles(
            [
                _candle("IHSG", date(2026, 7, 13)),  # Mon
                _candle("IHSG", date(2026, 7, 14)),  # Tue
                _candle("IHSG", date(2026, 7, 15)),  # Wed
                _candle("IHSG", date(2026, 7, 16)),  # Thu
                _candle("IHSG", date(2026, 7, 17)),  # future relative to coverage_end below
            ]
        )
        provider = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 13), coverage_end=date(2026, 7, 16))

        assert calendar is not None
        assert date(2026, 7, 17) not in calendar.sessions
        assert calendar.coverage_end == date(2026, 7, 16)


class TestUnexplainedWeekdayGapsAreUnavailable:
    """P0 fix: an absent weekday candle is ambiguous (IDX holiday? partial
    ingestion failure? quarantined/deleted row? provider omission?) and this
    repository has no independently authoritative session source to
    disambiguate it. The provider must therefore return unavailable rather
    than guess "holiday" — it must NOT preserve/invent a gap as a proven
    non-session day."""

    def test_unexplained_weekday_gap_makes_the_calendar_unavailable(self, tmp_path: Path):
        """Monday is absent from the cache. Even though get_date_range
        proves the cache spans the whole window, that is not proof the gap
        is a holiday rather than a data hole — the provider must return
        None, not a calendar with the gap silently treated as a holiday."""
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles(
            [
                _candle("IHSG", date(2026, 7, 17)),  # Friday
                # 2026-07-20 (Monday) deliberately absent and UNEXPLAINED
                _candle("IHSG", date(2026, 7, 21)),  # Tuesday
                _candle("IHSG", date(2026, 7, 22)),
                _candle("IHSG", date(2026, 7, 23)),
                _candle("IHSG", date(2026, 7, 24)),
            ]
        )
        provider = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 17), coverage_end=date(2026, 7, 24))

        assert calendar is None

    def test_gap_free_window_still_succeeds(self, tmp_path: Path):
        """Regression guard: a window with every weekday present must still
        succeed — the P0 fix must not make the provider always fail."""
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles(
            [
                _candle("IHSG", date(2026, 7, 17)),  # Friday
                _candle("IHSG", date(2026, 7, 20)),  # Monday
            ]
        )
        provider = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 17), coverage_end=date(2026, 7, 20))

        assert calendar is not None
        assert calendar.sessions == (date(2026, 7, 17), date(2026, 7, 20))


class TestDuplicateBenchmarkDates:
    def test_duplicate_candle_rows_do_not_duplicate_session_count(self):
        fake = FakeMarketRepository(
            {
                "IHSG": [
                    _candle("IHSG", date(2026, 7, 16), close=100),
                    _candle("IHSG", date(2026, 7, 16), close=101),  # duplicate date, different row
                ]
            }
        )
        provider = IHSGTradingSessionCalendarProvider(fake, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 16), coverage_end=date(2026, 7, 16))

        assert calendar is not None
        assert calendar.sessions == (date(2026, 7, 16),)


class TestMissingData:
    def test_missing_ihsg_data_returns_unavailable(self, tmp_path: Path):
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        provider = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES)

        calendar = provider.load(coverage_start=date(2026, 7, 1), coverage_end=date(2026, 7, 31))

        assert calendar is None

    def test_partial_cache_coverage_returns_unavailable_not_a_sparse_calendar(self, tmp_path: Path):
        """Cache only covers half the requested window — an absent candle
        inside the uncovered half could mean 'holiday' or 'never fetched';
        the provider must refuse to guess."""
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles([_candle("IHSG", date(2026, 7, 20))])

        calendar = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES).load(
            coverage_start=date(2026, 7, 1), coverage_end=date(2026, 7, 31)
        )

        assert calendar is None


class TestLegacyAliasFallback:
    def test_legacy_fallback_does_not_merge_incompatible_partial_canonical_data(
        self, tmp_path: Path
    ):
        """Canonical IHSG only has partial coverage (insufficient on its
        own), while legacy ^JKSE has full coverage with a different session
        date. The result must be exactly the legacy set — never a union
        that mixes the canonical ticker's partial/unproven data in."""
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        repo.save_candles([_candle("IHSG", date(2026, 7, 20))])  # partial only
        repo.save_candles([_candle("^JKSE", date(2026, 7, 17))])  # full-coverage legacy source

        calendar = IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES).load(
            coverage_start=date(2026, 7, 17), coverage_end=date(2026, 7, 17)
        )

        assert calendar is not None
        assert calendar.sessions == (date(2026, 7, 17),)

    def test_no_legacy_fallback_when_legacy_alias_is_none(self, tmp_path: Path):
        repo = SQLiteMarketRepository(db_path=tmp_path / "market.db")
        no_legacy = BenchmarkTickerAliases(canonical="IHSG", legacy=None)

        calendar = IHSGTradingSessionCalendarProvider(repo, benchmark=no_legacy).load(
            coverage_start=date(2026, 7, 1), coverage_end=date(2026, 7, 31)
        )

        assert calendar is None


class TestNoWrites:
    def test_provider_performs_no_writes(self, tmp_path: Path):
        db_path = tmp_path / "market.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        repo.save_candles([_candle("IHSG", date(2026, 7, 16))])
        mtime_before = db_path.stat().st_mtime_ns

        IHSGTradingSessionCalendarProvider(repo, benchmark=ALIASES).load(
            coverage_start=date(2026, 7, 1), coverage_end=date(2026, 7, 31)
        )

        assert db_path.stat().st_mtime_ns == mtime_before
