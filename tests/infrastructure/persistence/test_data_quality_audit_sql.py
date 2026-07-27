"""Tests for SQLite data-quality audit SQL helpers and probes."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from src.infrastructure.persistence.data_quality_audit_catalog import (
    ENRICHMENT_TABLE_SPECS,
)
from src.infrastructure.persistence.data_quality_audit_sql import (
    bad_candle_rows,
    count_rows,
    empty_analyst_rows,
    enrichment_snapshots,
    forward_estimates_missing_pe_rows,
    parse_date,
    table_snapshot,
    unknown_candle_provenance_rows,
    unsafe_broker_summary_rows,
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def test_table_snapshot_missing_table_returns_none(conn):
    assert (
        table_snapshot(
            conn,
            "candles",
            "date",
            tickers=["BBCA"],
            expected_trading_day=None,
        )
        is None
    )


def test_table_snapshot_counts_latest_missing_and_stale_tickers(conn):
    conn.execute("CREATE TABLE candles (ticker TEXT, date TEXT)")
    conn.executemany(
        "INSERT INTO candles (ticker, date) VALUES (?, ?)",
        [
            ("BBCA", "2026-07-15"),
            ("BBCA", "2026-07-14"),
            ("BBRI", "2026-07-10"),
        ],
    )
    conn.commit()

    snapshot = table_snapshot(
        conn,
        "candles",
        "date",
        tickers=["BBCA", "BBRI", "TLKM"],
        expected_trading_day=date(2026, 7, 15),
    )

    assert snapshot.rows == 3
    assert snapshot.tickers == 2
    assert snapshot.latest == date(2026, 7, 15)
    assert snapshot.missing_tickers == 1
    assert snapshot.stale_tickers == 1


def test_count_rows_missing_table_returns_zero(conn):
    assert count_rows(conn, "broker_summaries", tickers=[]) == 0


def test_unsafe_broker_summary_rows_uses_existing_predicate(conn):
    conn.execute("""
        CREATE TABLE broker_summaries (
            ticker TEXT, total_value TEXT, total_lot INTEGER,
            foreign_buy_lot INTEGER, foreign_sell_lot INTEGER
        )
        """)
    conn.executemany(
        "INSERT INTO broker_summaries VALUES (?, ?, ?, ?, ?)",
        [
            ("BBCA", "100", 10, 5, 5),  # safe
            ("BBCA", "0", 10, 5, 5),  # zero total_value
            ("BBCA", "-1", 10, 5, 5),  # negative total_value
            ("BBCA", "100", -1, 5, 5),  # negative total_lot
            ("BBCA", "100", 10, -1, 5),  # negative foreign_buy_lot
            ("BBCA", "100", 10, 5, -1),  # negative foreign_sell_lot
        ],
    )
    conn.commit()

    assert unsafe_broker_summary_rows(conn, []) == 5


def test_bad_candle_rows_uses_existing_predicate(conn):
    conn.execute(
        "CREATE TABLE candles "
        "(ticker TEXT, volume INTEGER, open TEXT, high TEXT, low TEXT, close TEXT)"
    )
    conn.executemany(
        "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("BBCA", 100, "10", "12", "9", "11"),  # safe
            ("BBCA", -1, "10", "12", "9", "11"),  # negative volume
            ("BBCA", 100, "0", "12", "9", "11"),  # open <= 0
            ("BBCA", 100, "10", "5", "9", "11"),  # high < max(open, close)
            ("BBCA", 100, "10", "12", "15", "11"),  # low > min(open, close)
        ],
    )
    conn.commit()

    assert bad_candle_rows(conn, []) == 4


def test_unknown_candle_provenance_requires_columns(conn):
    conn.execute("CREATE TABLE candles (ticker TEXT)")
    conn.commit()
    assert unknown_candle_provenance_rows(conn, []) == 0

    conn.execute("ALTER TABLE candles ADD COLUMN source TEXT")
    conn.execute("ALTER TABLE candles ADD COLUMN volume_unit TEXT")
    conn.execute("ALTER TABLE candles ADD COLUMN price_adjustment_policy TEXT")
    conn.executemany(
        "INSERT INTO candles (ticker, source, volume_unit, price_adjustment_policy) "
        "VALUES (?, ?, ?, ?)",
        [
            ("BBCA", "idx", "lot", "adjusted"),
            ("BBCA", "unknown", "lot", "adjusted"),
            ("BBCA", "idx", "unknown", "adjusted"),
            ("BBCA", "idx", "lot", "unknown"),
        ],
    )
    conn.commit()

    assert unknown_candle_provenance_rows(conn, []) == 3


def test_enrichment_snapshots_iterates_catalog_and_skips_missing_tables(conn):
    first_table, first_date_column = ENRICHMENT_TABLE_SPECS[0]
    third_table, third_date_column = ENRICHMENT_TABLE_SPECS[2]

    conn.execute(f"CREATE TABLE {first_table} (ticker TEXT, {first_date_column} TEXT)")
    conn.execute(f"INSERT INTO {first_table} VALUES ('BBCA', '2026-07-01')")
    conn.execute(f"CREATE TABLE {third_table} (ticker TEXT, {third_date_column} TEXT)")
    conn.execute(f"INSERT INTO {third_table} VALUES ('BBCA', '2026-07-02')")
    conn.commit()

    snapshots = enrichment_snapshots(conn, [])

    assert [s.table for s in snapshots] == [first_table, third_table]


def test_empty_analyst_rows_and_forward_estimates_missing_pe_rows(conn):
    conn.execute(
        "CREATE TABLE analyst_cache "
        "(ticker TEXT, buy_count INTEGER, hold_count INTEGER, sell_count INTEGER)"
    )
    conn.executemany(
        "INSERT INTO analyst_cache VALUES (?, ?, ?, ?)",
        [
            ("BBCA", 1, 0, 0),
            ("BBRI", 0, 0, 0),
        ],
    )
    conn.execute(
        "CREATE TABLE forward_estimates_cache (ticker TEXT, forward_eps_1y REAL, forward_pe REAL)"
    )
    conn.executemany(
        "INSERT INTO forward_estimates_cache VALUES (?, ?, ?)",
        [
            ("BBCA", 100.0, 10.0),
            ("BBRI", 100.0, None),
            ("TLKM", None, None),
        ],
    )
    conn.commit()

    assert empty_analyst_rows(conn, []) == 1
    assert forward_estimates_missing_pe_rows(conn, []) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("2026-07-15", date(2026, 7, 15)),
        ("2026-07-15T10:20:30", date(2026, 7, 15)),
        ("2026-07", date(2026, 7, 1)),
        ("not-a-date", None),
    ],
)
def test_parse_date_preserves_existing_formats(raw, expected):
    assert parse_date(raw) == expected
