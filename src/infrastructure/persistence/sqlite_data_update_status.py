"""
SQLite read model for `saham fetch market` post-run database status.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from src.application.use_case.data_update_status_use_case import DataUpdateTableStatus
from src.infrastructure.persistence.data_update_status_catalog import (
    DataUpdateTableSpec,
    build_data_update_table_specs,
)
from src.infrastructure.persistence.data_update_status_freshness import (
    freshness_status,
    range_label,
)


def build_data_update_table_statuses(
    db_path: Path,
    tickers: list[str],
    *,
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
    enrichment_available: bool,
    expected_trading_day: date | None,
    today: date | None = None,
    market_is_open: bool = False,
) -> list[DataUpdateTableStatus]:
    """
    Return dynamic status for every table `saham fetch market` may touch.

    The result is scoped to the stock tickers in the current run. Index tickers
    such as IHSG are intentionally excluded by the caller for non-candle tables.
    """
    today = today or date.today()
    stock_tickers = [t.upper() for t in tickers if not t.startswith("^")]

    specs = build_data_update_table_specs(
        candles_provider=candles_provider,
        broker_provider_name=broker_provider_name,
        no_meta=no_meta,
        candles_only=candles_only,
        broker_only=broker_only,
        enrichment_available=enrichment_available,
    )

    if not db_path.exists():
        return [
            DataUpdateTableStatus(
                table=spec.table,
                source=spec.source,
                rows=None,
                tickers=None,
                range_label="-",
                status="missing-db",
                contains=spec.contains,
                impact="No SQLite database exists.",
                issue="database file was not created",
            )
            for spec in specs
            if spec.applicable
        ]

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [
            _status_for_spec(
                conn,
                spec,
                stock_tickers,
                expected_trading_day=expected_trading_day,
                today=today,
                market_is_open=market_is_open,
            )
            for spec in specs
        ]


def _status_for_spec(
    conn: sqlite3.Connection,
    spec: DataUpdateTableSpec,
    tickers: list[str],
    *,
    expected_trading_day: date | None,
    today: date,
    market_is_open: bool = False,
) -> DataUpdateTableStatus:
    if not spec.applicable:
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=None,
            tickers=None,
            range_label="-",
            status="skipped",
            contains=spec.contains,
            impact=f"Skipped ({spec.skipped_reason}).",
        )

    if not _table_exists(conn, spec.table):
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=0,
            tickers=0,
            range_label="-",
            status="missing",
            contains=spec.contains,
            impact="No rows available for this run.",
            issue=f"{spec.table} table does not exist",
        )

    if not tickers:
        return DataUpdateTableStatus(
            table=spec.table,
            source=spec.source,
            rows=0,
            tickers=0,
            range_label="-",
            status="n/a",
            contains=spec.contains,
            impact="No stock tickers in this run.",
        )

    placeholders = ",".join("?" * len(tickers))
    where = f"ticker IN ({placeholders})"
    params: list[object] = list(tickers)
    if spec.source_column and spec.source_value:
        where += f" AND {spec.source_column} = ?"
        params.append(spec.source_value)

    row = conn.execute(
        f"""
        SELECT COUNT(*) AS rows,
               COUNT(DISTINCT ticker) AS tickers,
               MIN({spec.date_column}) AS min_date,
               MAX({spec.date_column}) AS max_date
        FROM {spec.table}
        WHERE {where}
        """,
        params,
    ).fetchone()

    rows = int(row["rows"] or 0)
    ticker_count = int(row["tickers"] or 0)
    min_raw = row["min_date"]
    max_raw = row["max_date"]
    range_label_val = range_label(min_raw, max_raw)
    status, impact, issue = freshness_status(
        table=spec.table,
        freshness=spec.freshness,
        rows=rows,
        ticker_count=ticker_count,
        requested_tickers=len(tickers),
        max_raw=max_raw,
        expected_trading_day=expected_trading_day,
        today=today,
        market_is_open=market_is_open,
    )

    return DataUpdateTableStatus(
        table=spec.table,
        source=spec.source,
        rows=rows,
        tickers=ticker_count,
        range_label=range_label_val,
        status=status,
        contains=spec.contains,
        impact=impact,
        issue=issue,
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None
