"""
SQLite read model for deterministic data-quality audit.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.application.use_case.data_quality_audit_use_case import (
    DataQualityRawSnapshot,
)
from src.domain.value_objects.benchmark_symbol import (
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_IHSG_TICKER,
)
from src.infrastructure.persistence.data_quality_audit_catalog import (
    CANDLE_PROVENANCE_COLUMNS,
)
from src.infrastructure.persistence.data_quality_audit_sql import (
    bad_candle_rows,
    count_rows,
    empty_analyst_rows,
    enrichment_snapshots,
    forward_estimates_missing_pe_rows,
    has_columns,
    latest_date,
    table_snapshot,
    unknown_candle_provenance_rows,
    unsafe_broker_summary_rows,
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
            expected = latest_date(
                conn,
                "candles",
                "date",
                ticker=CANONICAL_BENCHMARK_TICKER,
            )
            if expected is None:
                # Compatibility for databases not yet migrated to canonical IHSG.
                expected = latest_date(
                    conn,
                    "candles",
                    "date",
                    ticker=YAHOO_IHSG_TICKER,
                )
            if expected is None:
                expected = latest_date(conn, "candles", "date")

            return DataQualityRawSnapshot(
                database_exists=True,
                expected_trading_day=expected,
                candles=table_snapshot(
                    conn,
                    "candles",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                ),
                broker_summaries_idx=table_snapshot(
                    conn,
                    "broker_summaries",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="idx",
                ),
                foreign_flow_stockbit=table_snapshot(
                    conn,
                    "foreign_flow_points",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="stockbit",
                ),
                broker_daily_flow_stockbit=table_snapshot(
                    conn,
                    "broker_daily_flow",
                    "date",
                    tickers=normalized_tickers,
                    expected_trading_day=expected,
                    source_column="source",
                    source_value="stockbit",
                ),
                stockbit_summary_rows=count_rows(
                    conn,
                    "broker_summaries",
                    tickers=normalized_tickers,
                    where_extra="source = ?",
                    params_extra=["stockbit"],
                ),
                unsafe_broker_summary_rows=unsafe_broker_summary_rows(conn, normalized_tickers),
                bad_candle_rows=bad_candle_rows(conn, normalized_tickers),
                candle_source_columns_present=has_columns(
                    conn,
                    "candles",
                    CANDLE_PROVENANCE_COLUMNS,
                ),
                unknown_candle_provenance_rows=unknown_candle_provenance_rows(
                    conn,
                    normalized_tickers,
                ),
                enrichment_tables=enrichment_snapshots(
                    conn,
                    normalized_tickers,
                ),
                empty_analyst_rows=empty_analyst_rows(conn, normalized_tickers),
                forward_estimates_missing_pe_rows=forward_estimates_missing_pe_rows(
                    conn,
                    normalized_tickers,
                ),
            )
