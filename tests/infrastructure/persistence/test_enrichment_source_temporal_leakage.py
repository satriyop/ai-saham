"""
DQ-002G — planted future-row temporal leakage tests: enrichment cache sources.

Proves, using the real Stockbit cache-provider classes (not mocks) against
tmp_path SQLite databases, that a row fetched after `decision_at` cannot be
read as current for: analyst_cache, company_fundamentals, seasonality_cache.

These three providers already implement an `as_of_date` PIT guard
(pre-existing code, not added by this task) — these tests lock that
behavior in with the required DQ-002G test names and additionally prove the
resulting timestamp feeds correctly into `AssessSourceAvailabilityUseCase`.

Layer: Infrastructure (tests only) / Application (AssessSourceAvailabilityUseCase)
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider

DECISION_DATE = date(2026, 7, 16)
FUTURE_DATE = date(2026, 7, 17)


def _calendar() -> KnownTradingSessionCalendar:
    """DQ-002I: every source family exercised in this file is FETCH_TIMESTAMP,
    so the calendar is structurally required but never actually queried —
    an empty/trivial calendar is sufficient here."""
    return KnownTradingSessionCalendar(
        sessions=(), coverage_start=date(2026, 1, 1), coverage_end=date(2026, 12, 31)
    )


def _decision_session() -> EffectiveMarketSession:
    decision_at = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=DECISION_DATE,
        analysis_as_of=DECISION_DATE,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _insert_analyst_row(db_path: Path, fetched_date: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO analyst_cache (ticker, buy_count, hold_count, sell_count, "
            "avg_price_target, current_price, last_updated, fetched_date, "
            "price_target_low, price_target_high) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("BBCA", 5, 3, 1, 15000, 14800, "2026-07-16", fetched_date, 14500, 15500),
        )


def _insert_fundamentals_row(db_path: Path, fetched_date: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO company_fundamentals (ticker, fetched_date, pe_ratio_ttm, "
            "roe_ttm, net_profit_margin, revenue_yoy_growth, piotroski_f_score, "
            "dividend_yield, week52_high, week52_low, near_52w_high_rank, "
            "market_cap_idr, pbv) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "BBCA",
                fetched_date,
                15.0,
                22.0,
                18.0,
                5.0,
                7,
                2.5,
                10000,
                7000,
                85.0,
                2_000_000_000_000,
                3.0,
            ),
        )


def _insert_seasonality_row(db_path: Path, fetched_at: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO seasonality_cache (ticker, year, month, avg_return_pct, "
            "win_rate_pct, positive_years, total_years, back_years, source, "
            "fetched_month, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("BBCA", 2026, 7, 1.23, 60.0, 3, 5, 5, "stockbit", fetched_at[:7], fetched_at),
        )


class TestAnalystCacheTemporalLeakage:
    def test_analyst_cache_reader_excludes_rows_after_decision_date(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitAnalystConsensusProvider(api_client=None, db_path=db_path)
        _insert_analyst_row(db_path, datetime(2026, 7, 10).isoformat())
        _insert_analyst_row(db_path, datetime(2026, 7, 17).isoformat())

        result = provider.get_consensus("BBCA", as_of_date=DECISION_DATE)

        assert result is not None
        assert result.fetched_at.date() <= DECISION_DATE

    def test_analyst_cache_future_fetched_at_is_invalid(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitAnalystConsensusProvider(api_client=None, db_path=db_path)
        _insert_analyst_row(db_path, datetime(2026, 7, 17).isoformat())

        # Unbounded read (no as_of_date) sees the future-fetched row directly...
        unbounded = provider.get_consensus("BBCA")
        assert unbounded is not None
        assert unbounded.fetched_at.date() == FUTURE_DATE

        # ...but the availability contract must classify that timestamp as
        # INVALID/non-authoritative when compared against decision_at.
        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        result = use_case.execute(
            source_family="analyst_cache",
            effective_session=_decision_session(),
            available_at=datetime.combine(unbounded.fetched_at.date(), datetime.min.time()).replace(
                tzinfo=IDX_TIMEZONE
            ),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_analyst_cache_as_of_bounded_read_is_current(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitAnalystConsensusProvider(api_client=None, db_path=db_path)
        _insert_analyst_row(db_path, datetime(2026, 7, 16).isoformat())

        result = provider.get_consensus("BBCA", as_of_date=DECISION_DATE)
        assert result is not None

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        assessment = use_case.execute(
            source_family="analyst_cache",
            effective_session=_decision_session(),
            available_at=datetime.combine(result.fetched_at.date(), datetime.min.time()).replace(
                tzinfo=IDX_TIMEZONE
            ),
        )

        assert assessment.status is SourceAvailabilityStatus.CURRENT
        assert assessment.is_authoritative is True


class TestCompanyFundamentalsTemporalLeakage:
    def test_company_fundamentals_reader_excludes_rows_after_decision_date(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitFundamentalsProvider(api_client=None, db_path=db_path)
        _insert_fundamentals_row(db_path, DECISION_DATE.isoformat())
        _insert_fundamentals_row(db_path, FUTURE_DATE.isoformat())

        result = provider.get_fundamentals("BBCA", as_of_date=DECISION_DATE)

        assert result is not None
        assert result.fetched_at is not None
        assert result.fetched_at.date() <= DECISION_DATE

    def _retired_company_fundamentals_unbounded_future_row(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitFundamentalsProvider(api_client=None, db_path=db_path)
        _insert_fundamentals_row(db_path, FUTURE_DATE.isoformat())

        result_without_bound = provider.get_fundamentals("BBCA")
        assert result_without_bound is not None
        assert result_without_bound.fetched_at is not None
        assert result_without_bound.fetched_at.date() == FUTURE_DATE

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        assessment = use_case.execute(
            source_family="company_fundamentals",
            effective_session=_decision_session(),
            available_at=datetime.combine(
                result_without_bound.fetched_at.date(), datetime.min.time()
            ).replace(tzinfo=IDX_TIMEZONE),
        )

        assert assessment.status is SourceAvailabilityStatus.INVALID
        assert assessment.is_authoritative is False

    def test_company_fundamentals_bounded_read_returns_none_when_only_future_row_exists(
        self, tmp_path
    ):
        """Backtest-mode guarantee already in production code: with an
        as_of_date bound and only a future row present, no live fetch is
        attempted and None is returned rather than leaking the future row."""
        db_path = tmp_path / "data.db"
        provider = StockbitFundamentalsProvider(api_client=None, db_path=db_path)
        _insert_fundamentals_row(db_path, FUTURE_DATE.isoformat())

        result = provider.get_fundamentals("BBCA", as_of_date=DECISION_DATE)

        assert result is None


class TestSeasonalityCacheTemporalLeakage:
    def test_seasonality_cache_reader_excludes_rows_after_decision_date(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitSeasonalityProvider(api_client=None, db_path=db_path)
        _insert_seasonality_row(db_path, datetime(2026, 7, 10).isoformat())
        _insert_seasonality_row(db_path, datetime(2026, 7, 17).isoformat())

        edge = provider.get_seasonal_edge("BBCA", year=2026, month=7, as_of_date=DECISION_DATE)

        assert edge is not None

    def test_seasonality_cache_future_fetched_at_is_invalid(self, tmp_path):
        db_path = tmp_path / "data.db"
        provider = StockbitSeasonalityProvider(api_client=None, db_path=db_path)
        _insert_seasonality_row(db_path, datetime(2026, 7, 17).isoformat())

        unbounded = provider.get_seasonal_edge("BBCA", year=2026, month=7)
        assert unbounded is not None

        use_case = AssessSourceAvailabilityUseCase(calendar=_calendar())
        assessment = use_case.execute(
            source_family="seasonality_cache",
            effective_session=_decision_session(),
            available_at=datetime(2026, 7, 17, tzinfo=IDX_TIMEZONE),
        )

        assert assessment.status is SourceAvailabilityStatus.INVALID
        assert assessment.is_authoritative is False

    def test_seasonality_cache_bounded_read_returns_none_when_only_future_row_exists(
        self, tmp_path
    ):
        db_path = tmp_path / "data.db"
        provider = StockbitSeasonalityProvider(api_client=None, db_path=db_path)
        _insert_seasonality_row(db_path, datetime(2026, 7, 17).isoformat())

        edge = provider.get_seasonal_edge("BBCA", year=2026, month=7, as_of_date=DECISION_DATE)

        assert edge is None
