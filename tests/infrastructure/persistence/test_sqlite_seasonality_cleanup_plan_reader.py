"""Tests for SQLiteSeasonalityCleanupPlanReader (DQ-001G) — raw facts only,
no invalid-row classification (that lives in BuildSeasonalityCleanupPlanUseCase)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.persistence.sqlite_seasonality_cleanup_plan_reader import (
    SQLiteSeasonalityCleanupPlanReader,
)


def _build_schema(db_path: Path) -> None:
    # Reuse the real provider's migration so the reader is tested against
    # the actual production schema, not a hand-rolled approximation.
    StockbitSeasonalityProvider(api_client=None, db_path=db_path)


def test_database_exists_false_for_missing_file(tmp_path: Path):
    reader = SQLiteSeasonalityCleanupPlanReader(tmp_path / "does_not_exist.db")

    assert reader.database_exists() is False


def test_observe_returns_not_exists_when_table_missing(tmp_path: Path):
    db_path = tmp_path / "data.db"
    sqlite3.connect(str(db_path)).close()  # file exists, but no tables

    reader = SQLiteSeasonalityCleanupPlanReader(db_path)
    observation = reader.observe_seasonality_cache()

    assert observation.exists is False
    assert observation.rows == ()


def test_observe_returns_raw_rows_unmodified(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("BBCA", 2026, 7, 1.23, 60.0, 3, 5, 5, "stockbit", "2026-07", "2026-07-01T00:00:00"),
        )
        conn.execute(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("BBRI", 2026, 8, None, None, None, None, None, None, "2026-08", None),
        )

    reader = SQLiteSeasonalityCleanupPlanReader(db_path)
    observation = reader.observe_seasonality_cache()

    assert observation.exists is True
    assert len(observation.rows) == 2

    bbca = next(r for r in observation.rows if r.ticker == "BBCA")
    assert bbca.year == 2026
    assert bbca.month == 7
    assert bbca.avg_return_pct == 1.23
    assert bbca.win_rate_pct == 60.0
    assert bbca.positive_years == 3
    assert bbca.total_years == 5
    assert bbca.back_years == 5
    assert bbca.source == "stockbit"
    assert bbca.fetched_month == "2026-07"
    assert bbca.fetched_at == "2026-07-01T00:00:00"

    bbri = next(r for r in observation.rows if r.ticker == "BBRI")
    assert bbri.avg_return_pct is None
    assert bbri.source is None
    assert bbri.fetched_at is None


def test_reader_does_not_mutate_database(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    mtime_before = db_path.stat().st_mtime_ns

    SQLiteSeasonalityCleanupPlanReader(db_path).observe_seasonality_cache()

    assert db_path.stat().st_mtime_ns == mtime_before
