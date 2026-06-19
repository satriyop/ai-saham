"""Tests for data update database status read model."""

import sqlite3
from datetime import date
from pathlib import Path

from src.infrastructure.persistence.sqlite_data_update_status import (
    build_data_update_table_statuses,
)


def _init_core_tables(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE candles (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open TEXT NOT NULL,
                high TEXT NOT NULL,
                low TEXT NOT NULL,
                close TEXT NOT NULL,
                volume INTEGER NOT NULL,
                PRIMARY KEY (ticker, date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE broker_summaries (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                foreign_buy_value TEXT NOT NULL,
                foreign_sell_value TEXT NOT NULL,
                foreign_buy_lot INTEGER NOT NULL,
                foreign_sell_lot INTEGER NOT NULL,
                total_value TEXT NOT NULL,
                total_lot INTEGER NOT NULL,
                PRIMARY KEY (ticker, date, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE foreign_flow_points (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                net_val TEXT NOT NULL,
                net_lot INTEGER NOT NULL,
                avg_price TEXT NOT NULL,
                PRIMARY KEY (ticker, date, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE analyst_cache (
                ticker TEXT PRIMARY KEY,
                buy_count INTEGER NOT NULL,
                hold_count INTEGER NOT NULL,
                sell_count INTEGER NOT NULL,
                fetched_date TEXT NOT NULL
            )
            """
        )


def test_status_reports_independent_touched_tables(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _init_core_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO candles VALUES ('BBCA','2026-06-18','1','1','1','1',1)"
        )
        conn.execute(
            """
            INSERT INTO broker_summaries
            VALUES ('BBCA','2026-06-18','idx','1','0',1,0,'1',1)
            """
        )
        conn.execute(
            """
            INSERT INTO foreign_flow_points
            VALUES ('BBCA','2026-06-18','stockbit','1',1,'1')
            """
        )
        conn.execute(
            "INSERT INTO analyst_cache VALUES ('BBCA',1,0,0,'2026-06-18')"
        )

    statuses = build_data_update_table_statuses(
        db_path,
        ["BBCA"],
        candles_provider="yahoo",
        broker_provider_name="stockbit-session",
        no_meta=False,
        candles_only=False,
        broker_only=False,
        enrichment_available=True,
        expected_trading_day=date(2026, 6, 18),
        today=date(2026, 6, 18),
    )
    by_table = {s.table: s for s in statuses}

    assert by_table["candles"].status == "ready"
    assert by_table["broker_summaries"].status == "ready"
    assert by_table["foreign_flow_points"].status == "ready"
    assert by_table["foreign_flow_points"].source == "stockbit-session"
    assert by_table["analyst_cache"].status == "ready"
    assert by_table["stock_meta"].status == "missing"
    assert by_table["broker_daily_flow"].status == "missing"


def test_status_marks_provider_specific_skips(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _init_core_tables(db_path)

    statuses = build_data_update_table_statuses(
        db_path,
        ["BBCA"],
        candles_provider="yahoo",
        broker_provider_name="idx",
        no_meta=True,
        candles_only=False,
        broker_only=False,
        enrichment_available=False,
        expected_trading_day=date(2026, 6, 18),
        today=date(2026, 6, 18),
    )
    by_table = {s.table: s for s in statuses}

    assert by_table["stock_meta"].status == "skipped"
    assert by_table["broker_daily_flow"].status == "skipped"
    assert by_table["analyst_cache"].status == "skipped"
