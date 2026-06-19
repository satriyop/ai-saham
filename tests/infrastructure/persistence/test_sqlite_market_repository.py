"""
Tests for SQLite market data repository.

These tests verify:
- CRUD operations
- Upsert behavior
- Date range queries
- Schema creation

Uses temporary in-memory database for isolation.
"""

import sqlite3
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.entities.candle import Candle
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

# --- Test Fixtures ---


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def repository(temp_db):
    """Create a repository with temp database."""
    return SQLiteMarketRepository(db_path=temp_db)


def make_candle(ticker: str, day: int, month: int = 1, year: int = 2024) -> Candle:
    """Create a test candle."""
    return Candle(
        ticker=ticker,
        date=date(year, month, day),
        open=Decimal("1000.00"),
        high=Decimal("1100.00"),
        low=Decimal("900.00"),
        close=Decimal("1050.00"),
        volume=100000,
    )


# --- Tests ---


class TestSQLiteMarketRepository:
    """Test SQLite repository operations."""

    def test_save_and_retrieve_candles(self, repository):
        """Should save and retrieve candles."""
        candles = [
            make_candle("BBCA", 1),
            make_candle("BBCA", 2),
            make_candle("BBCA", 3),
        ]

        repository.save_candles(candles)
        result = repository.get_candles("BBCA")

        assert len(result) == 3
        assert result[0].date == date(2024, 1, 1)
        assert result[2].date == date(2024, 1, 3)

    def test_upsert_updates_existing(self, repository):
        """Should update existing candles on conflict."""
        # Save initial
        repository.save_candles([make_candle("BBCA", 1)])

        # Save updated (same date, different values)
        updated = Candle(
            ticker="BBCA",
            date=date(2024, 1, 1),
            open=Decimal("2000.00"),
            high=Decimal("2100.00"),
            low=Decimal("1900.00"),
            close=Decimal("2050.00"),
            volume=200000,
        )
        repository.save_candles([updated])

        result = repository.get_candles("BBCA")

        assert len(result) == 1
        assert result[0].close == Decimal("2050.00")
        assert result[0].volume == 200000

    def test_filter_by_date_range(self, repository):
        """Should filter candles by date range."""
        candles = [make_candle("BBCA", i) for i in range(1, 11)]
        repository.save_candles(candles)

        result = repository.get_candles(
            "BBCA",
            start_date=date(2024, 1, 3),
            end_date=date(2024, 1, 7),
        )

        assert len(result) == 5
        assert result[0].date == date(2024, 1, 3)
        assert result[-1].date == date(2024, 1, 7)

    def test_get_date_range(self, repository):
        """Should return date range of stored data."""
        candles = [make_candle("BBCA", i) for i in range(1, 11)]
        repository.save_candles(candles)

        result = repository.get_date_range("BBCA")

        assert result == (date(2024, 1, 1), date(2024, 1, 10))

    def test_get_date_range_returns_none_when_empty(self, repository):
        """Should return None when no data exists."""
        result = repository.get_date_range("XXXX")
        assert result is None

    def test_has_data_returns_true_when_covered(self, repository):
        """Should return True when cache covers requested range."""
        candles = [make_candle("BBCA", i) for i in range(1, 20)]
        repository.save_candles(candles)

        result = repository.has_data(
            "BBCA",
            start_date=date(2024, 1, 5),
            end_date=date(2024, 1, 15),
        )

        assert result is True

    def test_has_data_returns_false_when_not_covered(self, repository):
        """Should return False when cache doesn't cover range."""
        candles = [make_candle("BBCA", i) for i in range(5, 10)]
        repository.save_candles(candles)

        result = repository.has_data(
            "BBCA",
            start_date=date(2024, 1, 1),  # Before cached data
            end_date=date(2024, 1, 15),
        )

        assert result is False

    def test_ticker_case_insensitive(self, repository):
        """Should treat tickers as case-insensitive."""
        repository.save_candles([make_candle("BBCA", 1)])

        result_upper = repository.get_candles("BBCA")
        result_lower = repository.get_candles("bbca")

        assert len(result_upper) == 1
        assert len(result_lower) == 1

    def test_multiple_tickers_isolated(self, repository):
        """Different tickers should be stored separately."""
        repository.save_candles([make_candle("BBCA", 1)])
        repository.save_candles([make_candle("BBRI", 1)])

        bbca = repository.get_candles("BBCA")
        bbri = repository.get_candles("BBRI")

        assert len(bbca) == 1
        assert len(bbri) == 1
        assert bbca[0].ticker == "BBCA"
        assert bbri[0].ticker == "BBRI"

    def test_empty_candles_list_no_error(self, repository):
        """Should handle empty candles list gracefully."""
        repository.save_candles([])  # Should not raise
        result = repository.get_candles("BBCA")
        assert result == []

    def test_creates_parent_directories(self, temp_db):
        """Should create parent directories if needed."""
        nested_path = temp_db.parent / "nested" / "deep" / "test.db"
        repo = SQLiteMarketRepository(db_path=nested_path)

        repo.save_candles([make_candle("BBCA", 1)])

        assert nested_path.exists()

    def test_decimal_precision_preserved(self, repository):
        """Should preserve decimal precision."""
        candle = Candle(
            ticker="BBCA",
            date=date(2024, 1, 1),
            open=Decimal("9876.54"),
            high=Decimal("9999.99"),
            low=Decimal("9000.01"),
            close=Decimal("9543.21"),
            volume=123456789,
        )
        repository.save_candles([candle])

        result = repository.get_candles("BBCA")

        assert result[0].open == Decimal("9876.54")
        assert result[0].high == Decimal("9999.99")
        assert result[0].low == Decimal("9000.01")
        assert result[0].close == Decimal("9543.21")

    def test_schema_includes_candle_provenance_columns(self, temp_db):
        """Should create candle provenance columns for new databases."""
        SQLiteMarketRepository(db_path=temp_db)

        with sqlite3.connect(temp_db) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(candles)")}

        assert {"source", "volume_unit", "price_adjustment_policy"}.issubset(columns)

    def test_migrates_legacy_candles_table_with_unknown_provenance(self, temp_db):
        """Should add provenance columns to existing candle tables conservatively."""
        with sqlite3.connect(temp_db) as conn:
            conn.execute("""
                CREATE TABLE candles (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, date)
                )
            """)
            conn.execute(
                """
                INSERT INTO candles (ticker, date, open, high, low, close, volume)
                VALUES ('BBCA', '2024-01-01', '100', '110', '90', '105', 1000)
                """
            )
            conn.commit()

        SQLiteMarketRepository(db_path=temp_db)

        with sqlite3.connect(temp_db) as conn:
            row = conn.execute(
                """
                SELECT source, volume_unit, price_adjustment_policy
                FROM candles
                WHERE ticker = 'BBCA'
                """
            ).fetchone()

        assert row == ("unknown", "unknown", "unknown")

    def test_save_candles_persists_provenance_metadata(self, repository, temp_db):
        """Should persist provider source, volume unit, and adjustment policy."""
        repository.save_candles(
            [make_candle("BBCA", 1)],
            source="idx",
            volume_unit="shares",
            price_adjustment_policy="raw",
        )

        with sqlite3.connect(temp_db) as conn:
            row = conn.execute(
                """
                SELECT source, volume_unit, price_adjustment_policy
                FROM candles
                WHERE ticker = 'BBCA'
                """
            ).fetchone()

        assert row == ("idx", "shares", "raw")
