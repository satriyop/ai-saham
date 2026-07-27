"""
Read-only SQLite observer for the DQ-001D enrichment/source-context
reconciliation audit.

Opens SQLite in read-only URI mode and never executes write/DDL statements.
Uses SQL aggregate queries only — never loads full tables into Python.
Sibling to sqlite_source_reconciliation_reader.py (DQ-001B core tables);
kept separate per table-family so neither file grows past the
AI_AGENT_CHECKLIST.md repository-module size guidance.

Every observer checks required columns via PRAGMA table_info before running
any query that references them. A table that exists but is missing a
required column returns exists=True, schema_sufficient=False, and the
missing column names — never a crash.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from src.application.dto.source_reconciliation_dto import (
    RawCorporateActionLinkageObservation,
    RawInsiderCacheObservation,
    RawPitCacheObservation,
    RawSeasonalityObservation,
    RawStockMetaObservation,
    RawTickerNotationObservation,
)

_MAX_SAMPLE_ROWS = 10

_FUNDAMENTALS_METRIC_COLUMNS = (
    "pe_ratio_ttm",
    "roe_ttm",
    "net_profit_margin",
    "revenue_yoy_growth",
    "piotroski_f_score",
    "dividend_yield",
    "market_cap_idr",
    "pbv",
)
_ANALYST_METRIC_COLUMNS = ("buy_count", "hold_count", "sell_count")
_FORWARD_ESTIMATES_METRIC_COLUMNS = ("forward_eps_1y", "current_price", "forward_pe")

# Required columns per table: everything each observer's SQL directly
# references outside of the already-column-existence-tolerant metric lists.
_SEASONALITY_REQUIRED_COLUMNS = (
    "ticker",
    "year",
    "month",
    "source",
    "fetched_at",
    "fetched_month",
    "avg_return_pct",
    "win_rate_pct",
    "positive_years",
    "total_years",
    "back_years",
)
_PIT_CACHE_REQUIRED_COLUMNS = ("ticker", "fetched_date")
_INSIDER_REQUIRED_COLUMNS = ("ticker", "name", "action_type", "transaction_date", "fetched_date")
_CORPORATE_ACTION_EVENTS_REQUIRED_COLUMNS = (
    "source",
    "event_type",
    "source_event_id",
    "ticker",
)
_CORPORATE_ACTION_EVENT_DATES_REQUIRED_COLUMNS = (
    "source",
    "event_type",
    "source_event_id",
    "ticker",
    "date_role",
    "event_date",
    "fetched_at",
)
_TICKER_NOTATION_REQUIRED_COLUMNS = ("ticker", "source", "fetched_date")
_STOCK_META_REQUIRED_COLUMNS = ("ticker", "source", "fetched_at", "sector", "industry")


class SQLiteEnrichmentReconciliationReader:
    """Read-only observer of enrichment/source-context reconciliation facts (DQ-001D)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def observe_seasonality(self) -> RawSeasonalityObservation:
        table = "seasonality_cache"
        if not self._db_path.exists():
            return RawSeasonalityObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawSeasonalityObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _SEASONALITY_REQUIRED_COLUMNS)
            if missing:
                return RawSeasonalityObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            invalid_source_condition = (
                "(source IS NULL OR source = '' OR lower(source) = 'unknown')"
            )
            invalid_source_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {invalid_source_condition}"
            ).fetchone()[0]
            invalid_source_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, year, month, source FROM {table} "
                f"WHERE {invalid_source_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            null_fetched_at_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE fetched_at IS NULL"
            ).fetchone()[0]
            null_fetched_at_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, year, month FROM {table} WHERE fetched_at IS NULL "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

            null_fetched_month_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE fetched_month IS NULL"
            ).fetchone()[0]

            mismatch_condition = (
                "fetched_month IS NOT NULL AND fetched_at IS NOT NULL "
                "AND fetched_month != substr(fetched_at, 1, 7)"
            )
            fetched_month_mismatch_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {mismatch_condition}"
            ).fetchone()[0]
            fetched_month_mismatch_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, fetched_month, fetched_at FROM {table} "
                f"WHERE {mismatch_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            all_metrics_null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE avg_return_pct IS NULL "
                "AND win_rate_pct IS NULL AND positive_years IS NULL "
                "AND total_years IS NULL AND back_years IS NULL"
            ).fetchone()[0]

        return RawSeasonalityObservation(
            exists=True,
            row_count=row_count,
            invalid_source_count=invalid_source_count,
            invalid_source_samples=invalid_source_samples,
            null_fetched_at_count=null_fetched_at_count,
            null_fetched_at_samples=null_fetched_at_samples,
            null_fetched_month_count=null_fetched_month_count,
            fetched_month_mismatch_count=fetched_month_mismatch_count,
            fetched_month_mismatch_samples=fetched_month_mismatch_samples,
            all_metrics_null_count=all_metrics_null_count,
        )

    def observe_company_fundamentals(self) -> RawPitCacheObservation:
        return self._observe_pit_cache("company_fundamentals", _FUNDAMENTALS_METRIC_COLUMNS)

    def observe_analyst_cache(self) -> RawPitCacheObservation:
        return self._observe_pit_cache("analyst_cache", _ANALYST_METRIC_COLUMNS)

    def observe_forward_estimates(self) -> RawPitCacheObservation:
        return self._observe_pit_cache("forward_estimates_cache", _FORWARD_ESTIMATES_METRIC_COLUMNS)

    def _observe_pit_cache(
        self, table: str, metric_columns: tuple[str, ...]
    ) -> RawPitCacheObservation:
        if not self._db_path.exists():
            return RawPitCacheObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawPitCacheObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _PIT_CACHE_REQUIRED_COLUMNS)
            if missing:
                return RawPitCacheObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_identity_condition = "(ticker IS NULL OR fetched_date IS NULL)"
            missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_identity_condition}"
            ).fetchone()[0]
            missing_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, fetched_date FROM {table} "
                f"WHERE {missing_identity_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} "
                "WHERE ticker IS NOT NULL AND fetched_date IS NOT NULL "
                "GROUP BY ticker, fetched_date HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, fetched_date, COUNT(*) AS duplicate_row_count FROM {table} "
                "WHERE ticker IS NOT NULL AND fetched_date IS NOT NULL "
                f"GROUP BY ticker, fetched_date HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            present_metrics = [c for c in metric_columns if c in columns]
            if present_metrics:
                all_null_condition = " AND ".join(f"{c} IS NULL" for c in present_metrics)
                all_metrics_null_count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {all_null_condition}"
                ).fetchone()[0]
                all_metrics_null_samples = self._rows_as_dicts(
                    conn,
                    f"SELECT ticker, fetched_date FROM {table} "
                    f"WHERE {all_null_condition} LIMIT {_MAX_SAMPLE_ROWS}",
                )
            else:
                all_metrics_null_count = 0
                all_metrics_null_samples = ()

        return RawPitCacheObservation(
            exists=True,
            row_count=row_count,
            missing_identity_count=missing_identity_count,
            missing_identity_samples=missing_identity_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            all_metrics_null_count=all_metrics_null_count,
            all_metrics_null_samples=all_metrics_null_samples,
        )

    def observe_insider_cache(self) -> RawInsiderCacheObservation:
        table = "insider_cache"
        if not self._db_path.exists():
            return RawInsiderCacheObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawInsiderCacheObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _INSIDER_REQUIRED_COLUMNS)
            if missing:
                return RawInsiderCacheObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_identity_condition = (
                "(ticker IS NULL OR name IS NULL OR action_type IS NULL "
                "OR transaction_date IS NULL OR fetched_date IS NULL)"
            )
            missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_identity_condition}"
            ).fetchone()[0]
            missing_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, name, action_type, transaction_date, fetched_date "
                f"FROM {table} WHERE {missing_identity_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            non_null_identity = (
                "ticker IS NOT NULL AND name IS NOT NULL AND action_type IS NOT NULL "
                "AND transaction_date IS NOT NULL AND fetched_date IS NOT NULL"
            )
            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} WHERE {non_null_identity} "
                "GROUP BY ticker, name, action_type, transaction_date, fetched_date "
                "HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, name, action_type, transaction_date, fetched_date, "
                f"COUNT(*) AS duplicate_row_count FROM {table} WHERE {non_null_identity} "
                "GROUP BY ticker, name, action_type, transaction_date, fetched_date "
                f"HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawInsiderCacheObservation(
            exists=True,
            row_count=row_count,
            missing_identity_count=missing_identity_count,
            missing_identity_samples=missing_identity_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
        )

    def observe_corporate_action_linkage(self) -> RawCorporateActionLinkageObservation:
        events_table = "corporate_action_events"
        dates_table = "corporate_action_event_dates"
        if not self._db_path.exists():
            return RawCorporateActionLinkageObservation(
                events_exists=False, event_dates_exists=False
            )

        with closing(self._connect()) as conn:
            events_exists = self._table_exists(conn, events_table)
            event_dates_exists = self._table_exists(conn, dates_table)

            if not events_exists or not event_dates_exists:
                return RawCorporateActionLinkageObservation(
                    events_exists=events_exists,
                    event_dates_exists=event_dates_exists,
                    events_row_count=(
                        conn.execute(f"SELECT COUNT(*) FROM {events_table}").fetchone()[0]
                        if events_exists
                        else 0
                    ),
                    event_dates_row_count=(
                        conn.execute(f"SELECT COUNT(*) FROM {dates_table}").fetchone()[0]
                        if event_dates_exists
                        else 0
                    ),
                )

            events_columns = self._columns(conn, events_table)
            dates_columns = self._columns(conn, dates_table)
            events_row_count = conn.execute(f"SELECT COUNT(*) FROM {events_table}").fetchone()[0]
            event_dates_row_count = conn.execute(f"SELECT COUNT(*) FROM {dates_table}").fetchone()[
                0
            ]

            events_missing = self._missing_columns(
                events_columns, _CORPORATE_ACTION_EVENTS_REQUIRED_COLUMNS
            )
            dates_missing = self._missing_columns(
                dates_columns, _CORPORATE_ACTION_EVENT_DATES_REQUIRED_COLUMNS
            )
            if events_missing or dates_missing:
                return RawCorporateActionLinkageObservation(
                    events_exists=True,
                    event_dates_exists=True,
                    events_schema_sufficient=not events_missing,
                    events_missing_columns=events_missing,
                    event_dates_schema_sufficient=not dates_missing,
                    event_dates_missing_columns=dates_missing,
                    events_row_count=events_row_count,
                    event_dates_row_count=event_dates_row_count,
                )

            join_condition = (
                "e.source = d.source AND e.event_type = d.event_type "
                "AND e.source_event_id = d.source_event_id AND e.ticker = d.ticker"
            )
            orphan_date_rows_count = conn.execute(
                f"SELECT COUNT(*) FROM {dates_table} d "
                f"LEFT JOIN {events_table} e ON {join_condition} "
                "WHERE e.source IS NULL"
            ).fetchone()[0]
            orphan_date_rows_samples = self._rows_as_dicts(
                conn,
                "SELECT d.source AS source, d.event_type AS event_type, "
                "d.source_event_id AS source_event_id, d.ticker AS ticker, "
                "d.date_role AS date_role "
                f"FROM {dates_table} d LEFT JOIN {events_table} e ON {join_condition} "
                f"WHERE e.source IS NULL LIMIT {_MAX_SAMPLE_ROWS}",
            )

            events_without_dates_count = conn.execute(
                f"SELECT COUNT(*) FROM {events_table} e "
                f"LEFT JOIN {dates_table} d ON {join_condition} "
                "WHERE d.source IS NULL"
            ).fetchone()[0]
            events_without_dates_samples = self._rows_as_dicts(
                conn,
                "SELECT e.source AS source, e.event_type AS event_type, "
                "e.source_event_id AS source_event_id, e.ticker AS ticker "
                f"FROM {events_table} e LEFT JOIN {dates_table} d ON {join_condition} "
                f"WHERE d.source IS NULL LIMIT {_MAX_SAMPLE_ROWS}",
            )

            null_event_date_count = conn.execute(
                f"SELECT COUNT(*) FROM {dates_table} WHERE event_date IS NULL"
            ).fetchone()[0]
            null_event_date_samples = self._rows_as_dicts(
                conn,
                "SELECT source, event_type, source_event_id, ticker, date_role "
                f"FROM {dates_table} WHERE event_date IS NULL LIMIT {_MAX_SAMPLE_ROWS}",
            )

            null_date_role_count = conn.execute(
                f"SELECT COUNT(*) FROM {dates_table} WHERE date_role IS NULL"
            ).fetchone()[0]

        return RawCorporateActionLinkageObservation(
            events_exists=True,
            event_dates_exists=True,
            events_row_count=events_row_count,
            event_dates_row_count=event_dates_row_count,
            orphan_date_rows_count=orphan_date_rows_count,
            orphan_date_rows_samples=orphan_date_rows_samples,
            events_without_dates_count=events_without_dates_count,
            events_without_dates_samples=events_without_dates_samples,
            null_event_date_count=null_event_date_count,
            null_event_date_samples=null_event_date_samples,
            null_date_role_count=null_date_role_count,
        )

    def observe_ticker_notation(self) -> RawTickerNotationObservation:
        table = "ticker_notation_cache"
        if not self._db_path.exists():
            return RawTickerNotationObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawTickerNotationObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _TICKER_NOTATION_REQUIRED_COLUMNS)
            if missing:
                return RawTickerNotationObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_provenance_condition = "(source IS NULL OR fetched_date IS NULL)"
            missing_provenance_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_provenance_condition}"
            ).fetchone()[0]
            missing_provenance_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, source, fetched_date FROM {table} "
                f"WHERE {missing_provenance_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawTickerNotationObservation(
            exists=True,
            row_count=row_count,
            missing_provenance_count=missing_provenance_count,
            missing_provenance_samples=missing_provenance_samples,
        )

    def observe_stock_meta(self) -> RawStockMetaObservation:
        table = "stock_meta"
        if not self._db_path.exists():
            return RawStockMetaObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawStockMetaObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _STOCK_META_REQUIRED_COLUMNS)
            if missing:
                return RawStockMetaObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_identity_condition = "(ticker IS NULL OR source IS NULL OR fetched_at IS NULL)"
            missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_identity_condition}"
            ).fetchone()[0]
            missing_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, source, fetched_at FROM {table} "
                f"WHERE {missing_identity_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} "
                "WHERE ticker IS NOT NULL AND fetched_at IS NOT NULL "
                "GROUP BY ticker, fetched_at HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, fetched_at, COUNT(*) AS duplicate_row_count FROM {table} "
                "WHERE ticker IS NOT NULL AND fetched_at IS NOT NULL "
                f"GROUP BY ticker, fetched_at HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            both_null_condition = "(sector IS NULL AND industry IS NULL)"
            both_sector_industry_null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {both_null_condition}"
            ).fetchone()[0]
            both_sector_industry_null_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, fetched_at FROM {table} "
                f"WHERE {both_null_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawStockMetaObservation(
            exists=True,
            row_count=row_count,
            missing_identity_count=missing_identity_count,
            missing_identity_samples=missing_identity_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            both_sector_industry_null_count=both_sector_industry_null_count,
            both_sector_industry_null_samples=both_sector_industry_null_samples,
        )

    def _missing_columns(self, columns: set[str], required: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(c for c in required if c not in columns)

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        return row is not None

    def _columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _rows_as_dicts(self, conn: sqlite3.Connection, query: str) -> tuple[dict, ...]:
        cursor = conn.execute(query)
        columns = [description[0] for description in cursor.description]
        return tuple(dict(zip(columns, row)) for row in cursor.fetchall())

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)
