"""
SQLite read model for deterministic data-quality audit.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from src.domain.value_objects.benchmark_symbol import (
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_BENCHMARK_TICKER,
)
from src.application.use_case.data_quality_audit_use_case import (
    DataQualityRawSnapshot,
    DataQualityTableSnapshot,
)


class SQLiteDataQualityAuditReader:
    """Read-only SQLite data-quality snapshot reader."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def load_snapshot(self, tickers: list[str] | None = None) -> DataQualityRawSnapshot:
        if not self._db_path.exists():
            return DataQualityRawSnapshot(
                database_exists=False,
                expected_trading_day=None,
                candles=None,
                broker_summaries_idx=None,
                foreign_flow_stockbit=None,
                broker_daily_flow_stockbit=None,
                stockbit_summary_rows=0,
                unsafe_broker_summary_rows=0,
                bad_candle_rows=0,
                candle_source_columns_present=False,
                unknown_candle_provenance_rows=0,
            )

        normalized_tickers = [t.upper() for t in tickers or []]
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            expected = _latest_date(
                conn,
                "candles",
                "date",
                ticker=CANONICAL_BENCHMARK_TICKER,
            )
            if expected is None:
                # Compatibility for databases not yet migrated to canonical IHSG.
                expected = _latest_date(
                    conn,
                    "candles",
                    "date",
                    ticker=YAHOO_BENCHMARK_TICKER,
                )
            if expected is None:
                expected = _latest_date(conn, "candles", "date")

            return DataQualityRawSnapshot(
                database_exists=True,
                expected_trading_day=expected,
                candles=_table_snapshot(
                    conn,
                    "candles",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                ),
                broker_summaries_idx=_table_snapshot(
                    conn,
                    "broker_summaries",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="idx",
                ),
                foreign_flow_stockbit=_table_snapshot(
                    conn,
                    "foreign_flow_points",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="stockbit",
                ),
                broker_daily_flow_stockbit=_table_snapshot(
                    conn,
                    "broker_daily_flow",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="stockbit",
                ),
                stockbit_summary_rows=_count_rows(
                    conn,
                    "broker_summaries",
                    tickers=normalized_tickers,
                    where_extra="source = ?",
                    params_extra=["stockbit"],
                ),
                unsafe_broker_summary_rows=_unsafe_broker_summary_rows(conn, normalized_tickers),
                bad_candle_rows=_bad_candle_rows(conn, normalized_tickers),
                candle_source_columns_present=_has_columns(
                    conn,
                    "candles",
                    {"source", "volume_unit", "price_adjustment_policy"},
                ),
                unknown_candle_provenance_rows=_unknown_candle_provenance_rows(
                    conn,
                    normalized_tickers,
                ),
                enrichment_tables=_enrichment_snapshots(
                    conn,
                    normalized_tickers,
                ),
                empty_analyst_rows=_empty_analyst_rows(conn, normalized_tickers),
                forward_estimates_missing_pe_rows=_forward_estimates_missing_pe_rows(
                    conn,
                    normalized_tickers,
                ),
            )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _has_columns(conn: sqlite3.Connection, table: str, columns: set[str]) -> bool:
    if not _table_exists(conn, table):
        return False
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return columns.issubset(existing)


def _ticker_where(tickers: list[str]) -> tuple[str, list[str]]:
    if not tickers:
        return "", []
    placeholders = ",".join("?" * len(tickers))
    return f"ticker IN ({placeholders})", list(tickers)


def _table_snapshot(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    *,
    tickers: list[str],
    expected_trading_day: date | None,
    source_column: str | None = None,
    source_value: str | None = None,
) -> DataQualityTableSnapshot | None:
    if not _table_exists(conn, table):
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
    latest = _parse_date(row["latest"])
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


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return column in {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _latest_date(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    *,
    ticker: str | None = None,
) -> date | None:
    if not _table_exists(conn, table):
        return None
    if ticker is None:
        row = conn.execute(f"SELECT MAX({date_column}) FROM {table}").fetchone()
    else:
        row = conn.execute(
            f"SELECT MAX({date_column}) FROM {table} WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    return _parse_date(row[0] if row else None)


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


def _count_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    tickers: list[str],
    where_extra: str | None = None,
    params_extra: list[object] | None = None,
) -> int:
    if not _table_exists(conn, table):
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


def _unsafe_broker_summary_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not _table_exists(conn, "broker_summaries"):
        return 0
    return _count_rows(
        conn,
        "broker_summaries",
        tickers=tickers,
        where_extra=(
            "CAST(total_value AS REAL) <= 0 OR total_lot < 0 "
            "OR foreign_buy_lot < 0 OR foreign_sell_lot < 0"
        ),
    )


def _bad_candle_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not _table_exists(conn, "candles"):
        return 0
    return _count_rows(
        conn,
        "candles",
        tickers=tickers,
        where_extra=(
            "volume < 0 OR CAST(open AS REAL) <= 0 "
            "OR CAST(high AS REAL) < max(CAST(open AS REAL), CAST(close AS REAL)) "
            "OR CAST(low AS REAL) > min(CAST(open AS REAL), CAST(close AS REAL))"
        ),
    )


def _unknown_candle_provenance_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not _has_columns(conn, "candles", {"source", "volume_unit", "price_adjustment_policy"}):
        return 0
    return _count_rows(
        conn,
        "candles",
        tickers=tickers,
        where_extra=(
            "source = 'unknown' OR volume_unit = 'unknown' "
            "OR price_adjustment_policy = 'unknown'"
        ),
    )


def _enrichment_snapshots(
    conn: sqlite3.Connection,
    tickers: list[str],
) -> tuple[DataQualityTableSnapshot, ...]:
    specs = (
        ("ticker_notation_cache", "fetched_at"),
        ("analyst_cache", "fetched_date"),
        ("insider_cache", "fetched_date"),
        ("seasonality_cache", "fetched_month"),
        ("corp_action_cache", "fetched_date"),
        ("shareholding_composition", "fetched_date"),
        ("bandar_detector", "session_date"),
        ("company_fundamentals", "fetched_date"),
        ("forward_estimates_cache", "fetched_date"),
    )
    snapshots: list[DataQualityTableSnapshot] = []
    for table, date_column in specs:
        snapshot = _table_snapshot(
            conn,
            table,
            date_column,
            tickers=tickers,
            expected_trading_day=None,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


def _empty_analyst_rows(conn: sqlite3.Connection, tickers: list[str]) -> int:
    if not _table_exists(conn, "analyst_cache"):
        return 0
    return _count_rows(
        conn,
        "analyst_cache",
        tickers=tickers,
        where_extra="buy_count + hold_count + sell_count = 0",
    )


def _forward_estimates_missing_pe_rows(
    conn: sqlite3.Connection,
    tickers: list[str],
) -> int:
    if not _table_exists(conn, "forward_estimates_cache"):
        return 0
    return _count_rows(
        conn,
        "forward_estimates_cache",
        tickers=tickers,
        where_extra="forward_eps_1y IS NOT NULL AND forward_pe IS NULL",
    )


def _parse_date(raw: object) -> date | None:
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
