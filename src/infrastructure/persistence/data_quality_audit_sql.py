"""Low-level SQLite helpers and data-quality probes.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import date

from src.application.use_case.data_quality_audit_use_case import (
    DataQualityTableSnapshot,
)
from src.infrastructure.persistence.data_quality_audit_catalog import (
    CANDLE_PROVENANCE_COLUMNS,
    ENRICHMENT_TABLE_SPECS,
)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def has_columns(conn: sqlite3.Connection, table: str, columns: set[str] | frozenset[str]) -> bool:
    if not table_exists(conn, table):
        return False
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return columns.issubset(existing)


def _ticker_where(tickers: list[str]) -> tuple[str, list[str]]:
    if not tickers:
        return "", []
    placeholders = ",".join("?" * len(tickers))
    return f"ticker IN ({placeholders})", list(tickers)


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not table_exists(conn, table):
        return False
    return column in {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_snapshot(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    *,
    tickers: list[str],
    expected_trading_day: date | None,
    source_column: str | None = None,
    source_value: str | None = None,
) -> DataQualityTableSnapshot | None:
    if not table_exists(conn, table):
        return None

    where_parts: list[str] = []
    params: list[object] = []
    ticker_where, ticker_params = _ticker_where(tickers)
    if ticker_where:
        where_parts.append(ticker_where)
        params.extend(ticker_params)
    if source_column and source_value:
        where_parts.append(f"{source_column} = ?")
        params.append(source_value)
    where = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS rows,
               COUNT(DISTINCT ticker) AS tickers,
               MAX({date_column}) AS latest
        FROM {table}
        {where}
        """,
        params,
    ).fetchone()
    latest = parse_date(row["latest"])
    stale_tickers = 0
    if expected_trading_day is not None and _table_has_column(conn, table, "ticker"):
        stale_tickers = _stale_ticker_count(
            conn,
            table,
            date_column,
            expected_trading_day,
            tickers=tickers,
            source_column=source_column,
            source_value=source_value,
        )

    return DataQualityTableSnapshot(
        table=table,
        rows=int(row["rows"] or 0),
        tickers=int(row["tickers"] or 0),
        latest=latest,
        stale_tickers=stale_tickers,
        missing_tickers=max(0, len(tickers) - int(row["tickers"] or 0)) if tickers else 0,
    )


def latest_date(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    *,
    ticker: str | None = None,
) -> date | None:
    if not table_exists(conn, table):
        return None
    if ticker is None:
        row = conn.execute(f"SELECT MAX({date_column}) FROM {table}").fetchone()
    else:
        row = conn.execute(
            f"SELECT MAX({date_column}) FROM {table} WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    return parse_date(row[0] if row else None)


def _stale_ticker_count(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    expected_trading_day: date,
    *,
    tickers: list[str],
    source_column: str | None,
    source_value: str | None,
) -> int:
    where_parts: list[str] = []
    params: list[object] = []
    ticker_where, ticker_params = _ticker_where(tickers)
    if ticker_where:
        where_parts.append(ticker_where)
        params.extend(ticker_params)
    if source_column and source_value:
        where_parts.append(f"{source_column} = ?")
        params.append(source_value)
    where = " WHERE " + " AND ".join(where_parts) if where_parts else ""
    rows = conn.execute(
        f"""
        SELECT ticker, MAX({date_column}) AS latest
        FROM {table}
        {where}
        GROUP BY ticker
        HAVING latest < ?
        """,
        [*params, expected_trading_day.isoformat()],
    ).fetchall()
    return len(rows)


def count_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    tickers: list[str],
    where_extra: str | None = None,
    params_extra: list[object] | None = None,
) -> int:
    if not table_exists(conn, table):
        return 0
    where_parts: list[str] = []
    params: list[object] = []
    ticker_where, ticker_params = _ticker_where(tickers)
    if ticker_where:
        where_parts.append(ticker_where)
        params.extend(ticker_params)
    if where_extra:
        where_parts.append(f"({where_extra})")
        params.extend(params_extra or [])
    where = " WHERE " + " AND ".join(where_parts) if where_parts else ""
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}{where}", params).fetchone()[0] or 0)


def unsafe_broker_summary_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not table_exists(conn, "broker_summaries"):
        return 0
    return count_rows(
        conn,
        "broker_summaries",
        tickers=tickers,
        where_extra=(
            "CAST(total_value AS REAL) <= 0 OR total_lot < 0 "
            "OR foreign_buy_lot < 0 OR foreign_sell_lot < 0"
        ),
    )


def bad_candle_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not table_exists(conn, "candles"):
        return 0
    return count_rows(
        conn,
        "candles",
        tickers=tickers,
        where_extra=(
            "volume < 0 OR CAST(open AS REAL) <= 0 "
            "OR CAST(high AS REAL) < max(CAST(open AS REAL), CAST(close AS REAL)) "
            "OR CAST(low AS REAL) > min(CAST(open AS REAL), CAST(close AS REAL))"
        ),
    )


def unknown_candle_provenance_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not has_columns(conn, "candles", CANDLE_PROVENANCE_COLUMNS):
        return 0
    return count_rows(
        conn,
        "candles",
        tickers=tickers,
        where_extra=(
            "source = 'unknown' OR volume_unit = 'unknown' OR price_adjustment_policy = 'unknown'"
        ),
    )


def enrichment_snapshots(
    conn: sqlite3.Connection,
    tickers: list[str],
) -> tuple[DataQualityTableSnapshot, ...]:
    snapshots: list[DataQualityTableSnapshot] = []
    for table, date_column in ENRICHMENT_TABLE_SPECS:
        snapshot = table_snapshot(
            conn,
            table,
            date_column,
            tickers=tickers,
            expected_trading_day=None,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


def empty_analyst_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not table_exists(conn, "analyst_cache"):
        return 0
    return count_rows(
        conn,
        "analyst_cache",
        tickers=tickers,
        where_extra="buy_count + hold_count + sell_count = 0",
    )


def forward_estimates_missing_pe_rows(
    conn: sqlite3.Connection,
    tickers: list[str],
) -> int:
    if not table_exists(conn, "forward_estimates_cache"):
        return 0
    return count_rows(
        conn,
        "forward_estimates_cache",
        tickers=tickers,
        where_extra="forward_eps_1y IS NOT NULL AND forward_pe IS NULL",
    )


def parse_date(raw: object) -> date | None:
    if raw is None:
        return None
    value = str(raw)
    for candidate in (value[:10], value):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    if len(value) == 7 and value[4] == "-":
        try:
            return date(int(value[:4]), int(value[5:7]), 1)
        except ValueError:
            return None
    return None
