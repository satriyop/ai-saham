"""
Read-only SQLite observer for the DQ-001B source reconciliation audit.

Opens SQLite in read-only URI mode and never executes write/DDL statements.
Uses SQL aggregate queries only — never loads full tables into Python.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from src.application.use_case.audit_source_reconciliation_use_case import (
    RawBrokerDailyFlowObservation,
    RawBrokerSummariesObservation,
    RawCandlesOhlcObservation,
    RawForeignFlowReconciliationObservation,
)

_MAX_SAMPLE_ROWS = 10
_TOLERANCE_IDR = 1.0

_FOREIGN_FLOW_POINTS_REQUIRED_COLUMNS = {"ticker", "date", "source", "net_val"}


class SQLiteSourceReconciliationReader:
    """Read-only observer of source reconciliation facts for the DQ-001B audit."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_candles_ohlc(self) -> RawCandlesOhlcObservation:
        if not self._db_path.exists():
            return RawCandlesOhlcObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, "candles"):
                return RawCandlesOhlcObservation(exists=False)

            columns = self._columns(conn, "candles")
            row_count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]

            identity_columns_present = {"ticker", "date"} <= columns
            price_columns_present = {"open", "high", "low", "close"} <= columns
            volume_column_present = "volume" in columns

            if (
                not identity_columns_present
                or not price_columns_present
                or not volume_column_present
            ):
                return RawCandlesOhlcObservation(
                    exists=True,
                    row_count=row_count,
                    identity_columns_present=identity_columns_present,
                    price_columns_present=price_columns_present,
                    volume_column_present=volume_column_present,
                )

            invalid_condition = (
                "NOT ("
                "CAST(high AS REAL) >= CAST(open AS REAL) AND "
                "CAST(high AS REAL) >= CAST(close AS REAL) AND "
                "CAST(high AS REAL) >= CAST(low AS REAL) AND "
                "CAST(low AS REAL) <= CAST(open AS REAL) AND "
                "CAST(low AS REAL) <= CAST(close AS REAL)"
                ")"
            )
            invalid_ohlc_count = conn.execute(
                f"SELECT COUNT(*) FROM candles WHERE {invalid_condition}"
            ).fetchone()[0]
            invalid_ohlc_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, date, open, high, low, close FROM candles "
                f"WHERE {invalid_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            negative_volume_count = conn.execute(
                "SELECT COUNT(*) FROM candles WHERE volume < 0"
            ).fetchone()[0]
            negative_volume_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, date, volume FROM candles WHERE volume < 0 "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

            provenance_columns = [
                c
                for c in ("source", "volume_unit", "price_adjustment_policy")
                if c in columns
            ]
            missing_provenance_columns = [
                c
                for c in ("source", "volume_unit", "price_adjustment_policy")
                if c not in columns
            ]

            if missing_provenance_columns:
                # A provenance column absent from the schema entirely means every
                # row is unverifiable for that dimension — treat as fully unknown
                # rather than crashing on a nonexistent column.
                unknown_provenance_count = row_count
                unknown_provenance_samples = self._rows_as_dicts(
                    conn,
                    "SELECT ticker, date"
                    + "".join(f", {c}" for c in provenance_columns)
                    + f" FROM candles LIMIT {_MAX_SAMPLE_ROWS}",
                )
            elif provenance_columns:
                unknown_condition = " OR ".join(
                    f"({c} IS NULL OR {c} = '' OR lower({c}) = 'unknown')"
                    for c in provenance_columns
                )
                unknown_provenance_count = conn.execute(
                    f"SELECT COUNT(*) FROM candles WHERE {unknown_condition}"
                ).fetchone()[0]
                unknown_provenance_samples = self._rows_as_dicts(
                    conn,
                    "SELECT ticker, date"
                    + "".join(f", {c}" for c in provenance_columns)
                    + f" FROM candles WHERE {unknown_condition} LIMIT {_MAX_SAMPLE_ROWS}",
                )
            else:
                unknown_provenance_count = 0
                unknown_provenance_samples = ()

            source_distribution = (
                self._distribution(conn, "candles", "source") if "source" in columns else {}
            )
            volume_unit_distribution = (
                self._distribution(conn, "candles", "volume_unit")
                if "volume_unit" in columns
                else {}
            )
            price_adjustment_policy_distribution = (
                self._distribution(conn, "candles", "price_adjustment_policy")
                if "price_adjustment_policy" in columns
                else {}
            )

        return RawCandlesOhlcObservation(
            exists=True,
            row_count=row_count,
            invalid_ohlc_count=invalid_ohlc_count,
            invalid_ohlc_samples=invalid_ohlc_samples,
            negative_volume_count=negative_volume_count,
            negative_volume_samples=negative_volume_samples,
            unknown_provenance_count=unknown_provenance_count,
            unknown_provenance_samples=unknown_provenance_samples,
            source_distribution=source_distribution,
            volume_unit_distribution=volume_unit_distribution,
            price_adjustment_policy_distribution=price_adjustment_policy_distribution,
        )

    def observe_broker_summaries(self) -> RawBrokerSummariesObservation:
        if not self._db_path.exists():
            return RawBrokerSummariesObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, "broker_summaries"):
                return RawBrokerSummariesObservation(exists=False)

            columns = self._columns(conn, "broker_summaries")
            row_count = conn.execute("SELECT COUNT(*) FROM broker_summaries").fetchone()[0]

            identity_columns_present = {"ticker", "date", "source"} <= columns
            value_columns_present = {
                "foreign_buy_value",
                "foreign_sell_value",
                "foreign_buy_lot",
                "foreign_sell_lot",
                "total_value",
            } <= columns

            if not identity_columns_present or not value_columns_present:
                return RawBrokerSummariesObservation(
                    exists=True,
                    row_count=row_count,
                    identity_columns_present=identity_columns_present,
                    value_columns_present=value_columns_present,
                )

            negative_condition = (
                "(CAST(foreign_buy_value AS REAL) < 0 OR CAST(foreign_sell_value AS REAL) < 0 "
                "OR foreign_buy_lot < 0 OR foreign_sell_lot < 0 "
                "OR CAST(total_value AS REAL) < 0)"
            )
            negative_value_count = conn.execute(
                f"SELECT COUNT(*) FROM broker_summaries WHERE {negative_condition}"
            ).fetchone()[0]
            negative_value_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, date, source, foreign_buy_value, foreign_sell_value, "
                "foreign_buy_lot, foreign_sell_lot, total_value FROM broker_summaries "
                f"WHERE {negative_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_identity_count = conn.execute(
                "SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                "SELECT COUNT(*) AS cnt FROM broker_summaries "
                "GROUP BY ticker, date, source HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, date, source, COUNT(*) AS duplicate_row_count "
                "FROM broker_summaries GROUP BY ticker, date, source HAVING "
                f"COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawBrokerSummariesObservation(
            exists=True,
            row_count=row_count,
            negative_value_count=negative_value_count,
            negative_value_samples=negative_value_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
        )

    def observe_broker_daily_flow(self) -> RawBrokerDailyFlowObservation:
        if not self._db_path.exists():
            return RawBrokerDailyFlowObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, "broker_daily_flow"):
                return RawBrokerDailyFlowObservation(exists=False)

            columns = self._columns(conn, "broker_daily_flow")
            row_count = conn.execute("SELECT COUNT(*) FROM broker_daily_flow").fetchone()[0]

            identity_columns_present = {"ticker", "date", "broker_code", "source"} <= columns
            value_columns_present = {"buy_value", "sell_value", "net_value"} <= columns

            if not identity_columns_present or not value_columns_present:
                return RawBrokerDailyFlowObservation(
                    exists=True,
                    row_count=row_count,
                    identity_columns_present=identity_columns_present,
                    value_columns_present=value_columns_present,
                )

            negative_condition = (
                "(CAST(buy_value AS REAL) < 0 OR CAST(sell_value AS REAL) < 0)"
            )
            negative_value_count = conn.execute(
                f"SELECT COUNT(*) FROM broker_daily_flow WHERE {negative_condition}"
            ).fetchone()[0]
            negative_value_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, date, broker_code, source, buy_value, sell_value "
                f"FROM broker_daily_flow WHERE {negative_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            mismatch_condition = (
                "ABS(CAST(net_value AS REAL) - "
                "(CAST(buy_value AS REAL) - CAST(sell_value AS REAL))) > "
                f"{_TOLERANCE_IDR}"
            )
            net_mismatch_count = conn.execute(
                f"SELECT COUNT(*) FROM broker_daily_flow WHERE {mismatch_condition}"
            ).fetchone()[0]
            net_mismatch_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, date, broker_code, source, buy_value, sell_value, net_value "
                f"FROM broker_daily_flow WHERE {mismatch_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_identity_count = conn.execute(
                "SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                "SELECT COUNT(*) AS cnt FROM broker_daily_flow "
                "GROUP BY ticker, date, broker_code, source HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, date, broker_code, source, COUNT(*) AS duplicate_row_count "
                "FROM broker_daily_flow GROUP BY ticker, date, broker_code, source HAVING "
                f"COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            broker_count_row = conn.execute(
                "SELECT MIN(c), MAX(c), AVG(c) FROM ("
                "SELECT COUNT(DISTINCT broker_code) AS c FROM broker_daily_flow "
                "GROUP BY ticker, date"
                ")"
            ).fetchone()
            distinct_broker_code_total = conn.execute(
                "SELECT COUNT(DISTINCT broker_code) FROM broker_daily_flow"
            ).fetchone()[0]

        return RawBrokerDailyFlowObservation(
            exists=True,
            row_count=row_count,
            negative_value_count=negative_value_count,
            negative_value_samples=negative_value_samples,
            net_mismatch_count=net_mismatch_count,
            net_mismatch_samples=net_mismatch_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            broker_code_count_min=broker_count_row[0],
            broker_code_count_max=broker_count_row[1],
            broker_code_count_avg=broker_count_row[2],
            distinct_broker_code_total=distinct_broker_code_total,
        )

    def observe_foreign_flow_reconciliation(self) -> RawForeignFlowReconciliationObservation:
        if not self._db_path.exists():
            return RawForeignFlowReconciliationObservation(
                foreign_flow_points_exists=False,
                foreign_flow_points_schema_sufficient=False,
            )

        with closing(self._connect()) as conn:
            ffp_exists = self._table_exists(conn, "foreign_flow_points")
            snapshots_exists = self._table_exists(conn, "foreign_flow_snapshots")

            if not ffp_exists:
                return RawForeignFlowReconciliationObservation(
                    foreign_flow_points_exists=False,
                    foreign_flow_points_schema_sufficient=False,
                    foreign_flow_snapshots_exists=snapshots_exists,
                )

            ffp_columns = self._columns(conn, "foreign_flow_points")
            bs_columns = self._columns(conn, "broker_summaries")
            required_bs_columns = {
                "ticker",
                "date",
                "source",
                "foreign_buy_value",
                "foreign_sell_value",
            }
            schema_sufficient = _FOREIGN_FLOW_POINTS_REQUIRED_COLUMNS <= ffp_columns and (
                required_bs_columns <= bs_columns
            )

            if not schema_sufficient:
                return RawForeignFlowReconciliationObservation(
                    foreign_flow_points_exists=True,
                    foreign_flow_points_schema_sufficient=False,
                    foreign_flow_snapshots_exists=snapshots_exists,
                )

            total_row_count = conn.execute(
                "SELECT COUNT(*) FROM foreign_flow_points"
            ).fetchone()[0]

            matched_row_count = conn.execute(
                "SELECT COUNT(*) FROM foreign_flow_points ffp "
                "JOIN broker_summaries bs ON bs.ticker = ffp.ticker "
                "AND bs.date = ffp.date AND bs.source = ffp.source"
            ).fetchone()[0]
            unmatched_row_count = total_row_count - matched_row_count

            mismatch_condition = (
                "ABS(CAST(ffp.net_val AS REAL) - "
                "(CAST(bs.foreign_buy_value AS REAL) - CAST(bs.foreign_sell_value AS REAL))) > "
                f"{_TOLERANCE_IDR}"
            )
            mismatch_count = conn.execute(
                "SELECT COUNT(*) FROM foreign_flow_points ffp "
                "JOIN broker_summaries bs ON bs.ticker = ffp.ticker "
                "AND bs.date = ffp.date AND bs.source = ffp.source "
                f"WHERE {mismatch_condition}"
            ).fetchone()[0]
            mismatch_samples = self._rows_as_dicts(
                conn,
                "SELECT ffp.ticker AS ticker, ffp.date AS date, ffp.source AS source, "
                "ffp.net_val AS foreign_flow_points_net_val, "
                "(CAST(bs.foreign_buy_value AS REAL) - CAST(bs.foreign_sell_value AS REAL)) "
                "AS broker_summaries_derived_net_value "
                "FROM foreign_flow_points ffp "
                "JOIN broker_summaries bs ON bs.ticker = ffp.ticker "
                "AND bs.date = ffp.date AND bs.source = ffp.source "
                f"WHERE {mismatch_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawForeignFlowReconciliationObservation(
            foreign_flow_points_exists=True,
            foreign_flow_points_schema_sufficient=True,
            total_row_count=total_row_count,
            matched_row_count=matched_row_count,
            unmatched_row_count=unmatched_row_count,
            mismatch_count=mismatch_count,
            mismatch_samples=mismatch_samples,
            foreign_flow_snapshots_exists=snapshots_exists,
        )

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        return row is not None

    def _columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _distribution(self, conn: sqlite3.Connection, table: str, column: str) -> dict:
        rows = conn.execute(
            f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}"
        ).fetchall()
        return {(value if value is not None else "null"): count for value, count in rows}

    def _rows_as_dicts(self, conn: sqlite3.Connection, query: str) -> tuple[dict, ...]:
        cursor = conn.execute(query)
        columns = [description[0] for description in cursor.description]
        return tuple(dict(zip(columns, row)) for row in cursor.fetchall())

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)
