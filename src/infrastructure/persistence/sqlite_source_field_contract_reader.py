"""
Read-only SQLite observer for the DQ-001A source-field contract audit.

Opens SQLite in read-only URI mode and never executes write/DDL statements.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from src.application.use_case.audit_source_field_contracts_use_case import (
    RawFieldObservation,
    RawTableObservation,
    SourceFieldContract,
)
from src.infrastructure.persistence.source_field_contract_catalog import (
    DERIVED_FIELDS,
    FIELD_STATS_MODE,
    StaticSourceFieldContractCatalog,
)


class SQLiteSourceFieldContractReader:
    """Read-only observer of table/field facts for the DQ-001A audit."""

    def __init__(
        self,
        db_path: str | Path,
        catalog: StaticSourceFieldContractCatalog | None = None,
    ) -> None:
        self._db_path = Path(db_path).expanduser()
        self._catalog = catalog or StaticSourceFieldContractCatalog()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_table(self, table: str) -> RawTableObservation:
        if not self._db_path.exists():
            return RawTableObservation(table=table, exists=False)

        with closing(self._connect()) as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if table not in existing_tables:
                return RawTableObservation(table=table, exists=False)

            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            field_observations = tuple(
                self._observe_field(conn, table, contract, columns)
                for contract in self._catalog.contracts_for_table(table)
            )
            special_checks = self._compute_special_checks(conn, table, columns)

        return RawTableObservation(
            table=table,
            exists=True,
            row_count=row_count,
            fields=field_observations,
            special_checks=special_checks,
        )

    def _observe_field(
        self,
        conn: sqlite3.Connection,
        table: str,
        contract: SourceFieldContract,
        columns: set[str],
    ) -> RawFieldObservation:
        derived_from = DERIVED_FIELDS.get((table, contract.field))
        if derived_from:
            if not all(component in columns for component in derived_from):
                return RawFieldObservation(field=contract.field, exists=False)
            null_expr = " OR ".join(f"{component} IS NULL" for component in derived_from)
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {null_expr}"
            ).fetchone()[0]
            return RawFieldObservation(field=contract.field, exists=True, null_count=null_count)

        if contract.field not in columns:
            return RawFieldObservation(field=contract.field, exists=False)

        col = contract.field
        null_count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL").fetchone()[0]

        stats_mode = FIELD_STATS_MODE.get((table, col), "none")
        distinct_count: int | None = None
        min_value: str | None = None
        max_value: str | None = None

        if stats_mode in ("identity_text", "date", "enum_text"):
            distinct_count = conn.execute(
                f"SELECT COUNT(DISTINCT {col}) FROM {table}"
            ).fetchone()[0]

        if stats_mode == "date":
            row = conn.execute(
                f"SELECT MIN({col}), MAX({col}) FROM {table} WHERE {col} IS NOT NULL"
            ).fetchone()
            min_value, max_value = row[0], row[1]
        elif stats_mode == "numeric":
            row = conn.execute(
                f"SELECT MIN({col}), MAX({col}) FROM {table} WHERE {col} IS NOT NULL"
            ).fetchone()
            min_value = str(row[0]) if row[0] is not None else None
            max_value = str(row[1]) if row[1] is not None else None
        elif stats_mode == "numeric_text":
            row = conn.execute(
                f"SELECT MIN(CAST({col} AS REAL)), MAX(CAST({col} AS REAL)) "
                f"FROM {table} WHERE {col} IS NOT NULL"
            ).fetchone()
            min_value = str(row[0]) if row[0] is not None else None
            max_value = str(row[1]) if row[1] is not None else None

        invalid_value_count: int | None = None
        if contract.invalid_values:
            placeholders = ",".join("?" for _ in contract.invalid_values)
            invalid_value_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL "
                f"OR lower({col}) IN ({placeholders})",
                tuple(v.lower() for v in contract.invalid_values),
            ).fetchone()[0]

        return RawFieldObservation(
            field=col,
            exists=True,
            null_count=null_count,
            distinct_count=distinct_count,
            min_value=min_value,
            max_value=max_value,
            invalid_value_count=invalid_value_count,
        )

    def _compute_special_checks(
        self, conn: sqlite3.Connection, table: str, columns: set[str]
    ) -> dict[str, int]:
        checks: dict[str, int] = {}

        if table == "candidate_observations" and "config_hash" in columns:
            checks["legacy_config_hash_count"] = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE config_hash = ''"
            ).fetchone()[0]

        if table == "signal_forward_labels":
            if {"outcome_label", "unavailable_reason"} <= columns:
                checks["unavailable_without_reason_count"] = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE outcome_label = 'UNAVAILABLE' "
                    "AND (unavailable_reason IS NULL OR unavailable_reason = '')"
                ).fetchone()[0]
            if {"outcome_label", "close_return"} <= columns:
                checks["complete_label_null_return_count"] = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE outcome_label != 'UNAVAILABLE' "
                    "AND close_return IS NULL"
                ).fetchone()[0]

        return checks

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)
