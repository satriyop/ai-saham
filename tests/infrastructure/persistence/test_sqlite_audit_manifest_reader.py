"""Tests for SQLiteAuditManifestReader (DQ-000)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_audit_manifest_reader import (
    SQLiteAuditManifestReader,
)


def _build_temp_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE candles (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'unknown'
        )
        """)
    conn.executemany(
        "INSERT INTO candles (ticker, date, open, high, low, close, volume, source) "
        "VALUES (?, ?, '1', '1', '1', '1', 1, 'idx')",
        [
            ("BBCA", "2026-01-02"),
            ("BBCA", "2026-01-05"),
            ("BBCA", "2026-01-05"),  # duplicate (ticker, date, source)
            ("BBRI", "2026-01-03"),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "audit_manifest_test.db"
    _build_temp_db(db_path)
    return db_path


def test_database_identity_reports_hash_and_size(temp_db: Path):
    reader = SQLiteAuditManifestReader(temp_db)

    identity = reader.database_identity()

    assert identity.exists is True
    assert identity.path == str(temp_db)
    assert identity.sha256 is not None
    assert identity.size_bytes == temp_db.stat().st_size


def test_missing_database_reports_exists_false_and_warning():
    reader = SQLiteAuditManifestReader(Path("/nonexistent/does_not_exist.db"))

    identity = reader.database_identity()

    assert identity.exists is False
    assert identity.sha256 is None
    assert identity.size_bytes is None
    assert "database_missing" in reader.warnings()


def test_table_summaries_reports_row_count_dates_tickers_and_duplicates(temp_db: Path):
    reader = SQLiteAuditManifestReader(temp_db)

    summaries = reader.table_summaries()
    candles = next(s for s in summaries if s.table == "candles")

    assert candles.row_count == 4
    assert candles.min_date == "2026-01-02"
    assert candles.max_date == "2026-01-05"
    assert candles.ticker_count == 2
    assert candles.duplicate_key_count == 1  # one extra (BBCA, 2026-01-05, idx) row


def test_missing_table_is_skipped_with_warning(temp_db: Path):
    reader = SQLiteAuditManifestReader(temp_db)

    reader.table_summaries()

    assert "missing_table:broker_summaries" in reader.warnings()
    assert "missing_table:insider_cache" in reader.warnings()


def test_real_enrichment_table_names_are_recognized(tmp_path: Path):
    # Regression: the task template guessed "insider_activity_cache",
    # "fundamentals_cache", "shareholding_cache" — the live schema uses
    # "insider_cache", "company_fundamentals", "shareholding_composition".
    db_path = tmp_path / "enrichment.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE insider_cache (
            ticker TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            fetched_date TEXT NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE company_fundamentals (
            ticker TEXT NOT NULL,
            fetched_date TEXT NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE shareholding_composition (
            ticker TEXT NOT NULL,
            fetched_date TEXT NOT NULL
        )
        """)
    conn.execute(
        "INSERT INTO insider_cache VALUES ('BBCA', 'X', '2026-01-02', 'buy', '2026-01-03')"
    )
    conn.execute("INSERT INTO company_fundamentals VALUES ('BBCA', '2026-01-03')")
    conn.execute("INSERT INTO shareholding_composition VALUES ('BBCA', '2026-01-03')")
    conn.commit()
    conn.close()

    reader = SQLiteAuditManifestReader(db_path)
    summaries = {s.table: s for s in reader.table_summaries()}

    assert "insider_cache" in summaries
    assert "company_fundamentals" in summaries
    assert "shareholding_composition" in summaries
    assert summaries["insider_cache"].row_count == 1
    assert summaries["company_fundamentals"].min_date == "2026-01-03"
    assert summaries["shareholding_composition"].ticker_count == 1

    warnings = reader.warnings()
    assert "missing_table:insider_activity_cache" not in warnings
    assert "missing_table:fundamentals_cache" not in warnings
    assert "missing_table:shareholding_cache" not in warnings


def test_seasonality_cache_reports_fetched_month_as_date(tmp_path: Path):
    db_path = tmp_path / "seasonality.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE seasonality_cache (
            ticker TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            fetched_month TEXT NOT NULL,
            fetched_at TEXT
        )
        """)
    conn.executemany(
        "INSERT INTO seasonality_cache (ticker, year, month, fetched_month, fetched_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("BBCA", 2026, 1, "2026-01", "2026-01-05T00:00:00"),
            ("BBCA", 2026, 2, "2026-02", "2026-02-05T00:00:00"),
        ],
    )
    conn.commit()
    conn.close()

    reader = SQLiteAuditManifestReader(db_path)
    summaries = {s.table: s for s in reader.table_summaries()}

    assert summaries["seasonality_cache"].min_date == "2026-01"
    assert summaries["seasonality_cache"].max_date == "2026-02"
    assert "date_column_unknown:seasonality_cache" not in reader.warnings()


def test_reader_does_not_mutate_database(temp_db: Path):
    row_count_before = _row_count(temp_db, "candles")
    mtime_before = temp_db.stat().st_mtime_ns

    reader = SQLiteAuditManifestReader(temp_db)
    reader.database_identity()
    reader.schema_identity()
    reader.table_summaries()

    row_count_after = _row_count(temp_db, "candles")
    mtime_after = temp_db.stat().st_mtime_ns

    assert row_count_before == row_count_after
    assert mtime_before == mtime_after


def test_reader_opens_connection_in_read_only_mode(temp_db: Path, monkeypatch):
    reader = SQLiteAuditManifestReader(temp_db)

    real_connect = sqlite3.connect
    captured_uris: list[str] = []

    def spying_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            captured_uris.append(database)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spying_connect)

    reader.schema_identity()

    assert captured_uris, "expected a uri=True read-only connection"
    assert all("mode=ro" in uri for uri in captured_uris)

    # A read-only connection must reject writes.
    with real_connect(f"file:{temp_db}?mode=ro", uri=True) as ro_conn:
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute(
                "INSERT INTO candles (ticker, date, open, high, low, close, volume) "
                "VALUES ('X', '2026-01-01', '1', '1', '1', '1', 1)"
            )


def _row_count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()
