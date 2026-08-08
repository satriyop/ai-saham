"""
Read-only SQLite reader for the DQ-000 audit baseline manifest.

Opens SQLite in read-only URI mode and never executes write/DDL statements.

Layer: Infrastructure
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditDatabaseIdentity,
    AuditSchemaIdentity,
    AuditTableSummary,
)

_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class _TableAuditSpec:
    date_column: str | None
    identity_columns: tuple[str, ...] | None


# Minimum table coverage required by DQ-000. Tables not present in the
# database are skipped and reported via a "missing_table:<name>" warning
# rather than guessed at.
_TABLE_CATALOG: dict[str, _TableAuditSpec] = {
    "candles": _TableAuditSpec("date", ("ticker", "date", "source")),
    "broker_summaries": _TableAuditSpec("date", ("ticker", "date", "source")),
    "broker_daily_flow": _TableAuditSpec("date", ("ticker", "date", "broker_code", "source")),
    "learning_observations": _TableAuditSpec("cutoff_at", ("observation_id", "artifact_digest")),
    "learning_track_snapshots": _TableAuditSpec("sampled_at", ("snapshot_id", "observation_id")),
    "learning_outcome_labels": _TableAuditSpec("labeled_at", ("label_id", "observation_id")),
    "learning_evaluations": _TableAuditSpec(
        "evaluated_at", ("evaluation_id", "dataset_fingerprint")
    ),
    "learning_policy_proposals": _TableAuditSpec(
        "created_at", ("proposal_id", "source_evaluation_id")
    ),
    "learning_policy_validations": _TableAuditSpec(
        "validated_at", ("validation_id", "proposal_id")
    ),
    "learning_policy_applications": _TableAuditSpec(
        "applied_at", ("application_id", "proposal_id")
    ),
    "learning_policy_snapshots": _TableAuditSpec(
        "created_at", ("snapshot_id", "payload_digest", "compatibility_id", "policy_id")
    ),
    "learning_diagnostic_producer_snapshots": _TableAuditSpec(
        "created_at", ("snapshot_id", "payload_digest", "purpose", "producer_id")
    ),
    "stock_meta": _TableAuditSpec("fetched_at", ("ticker", "fetched_at")),
    "analyst_cache": _TableAuditSpec("fetched_date", ("ticker", "fetched_date")),
    # Task template named these tables "insider_activity_cache",
    # "fundamentals_cache", and "shareholding_cache", but the live schema
    # uses "insider_cache", "company_fundamentals", and
    # "shareholding_composition" (confirmed against
    # src/infrastructure/browser/stockbit_insider_cache.py,
    # stockbit_fundamentals_cache.py, stockbit_shareholding.py, and the
    # existing data_quality_audit_catalog.ENRICHMENT_TABLE_SPECS). Using the
    # verified names rather than the guessed ones so the manifest reports
    # real coverage instead of false "missing" findings.
    "insider_cache": _TableAuditSpec(
        "fetched_date",
        ("ticker", "name", "transaction_date", "action_type", "fetched_date"),
    ),
    "company_fundamentals": _TableAuditSpec("fetched_date", ("ticker", "fetched_date")),
    "shareholding_composition": _TableAuditSpec("fetched_date", ("ticker", "fetched_date")),
    # data_quality_audit_catalog.ENRICHMENT_TABLE_SPECS already treats
    # fetched_month as this table's freshness/date column.
    "seasonality_cache": _TableAuditSpec(
        "fetched_month",
        ("ticker", "year", "month", "fetched_month", "fetched_at"),
    ),
    "corporate_action_events": _TableAuditSpec(
        "fetched_at",
        ("source", "event_type", "source_event_id", "ticker"),
    ),
}

_AUDITED_TABLES = tuple(_TABLE_CATALOG.keys())


class SQLiteAuditManifestReader:
    """Read-only manifest reader. One instance audits one database snapshot."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._warnings: list[str] = []

    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def database_identity(self) -> AuditDatabaseIdentity:
        if not self._db_path.exists():
            self._warnings.append("database_missing")
            return AuditDatabaseIdentity(
                path=str(self._db_path),
                exists=False,
                sha256=None,
                size_bytes=None,
            )
        return AuditDatabaseIdentity(
            path=str(self._db_path),
            exists=True,
            sha256=_sha256_file(self._db_path),
            size_bytes=self._db_path.stat().st_size,
        )

    def schema_identity(self) -> AuditSchemaIdentity:
        if not self._db_path.exists():
            return AuditSchemaIdentity(sqlite_user_version=None, migration_count=None, tables=())

        with closing(self._connect()) as conn:
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = tuple(
                sorted(
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                )
            )
            migration_count = None
            if "_schema_migrations" in tables:
                migration_count = conn.execute(
                    "SELECT COUNT(*) FROM _schema_migrations"
                ).fetchone()[0]

        return AuditSchemaIdentity(
            sqlite_user_version=user_version,
            migration_count=migration_count,
            tables=tables,
        )

    def table_summaries(self) -> tuple[AuditTableSummary, ...]:
        if not self._db_path.exists():
            return ()

        summaries: list[AuditTableSummary] = []
        with closing(self._connect()) as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in _AUDITED_TABLES:
                if table not in existing_tables:
                    self._warnings.append(f"missing_table:{table}")
                    continue
                summaries.append(self._summarize_table(conn, table, _TABLE_CATALOG[table]))
        return tuple(summaries)

    def _summarize_table(
        self, conn: sqlite3.Connection, table: str, spec: _TableAuditSpec
    ) -> AuditTableSummary:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        min_date: str | None = None
        max_date: str | None = None
        if spec.date_column and spec.date_column in columns:
            row = conn.execute(
                f"SELECT MIN({spec.date_column}), MAX({spec.date_column}) FROM {table}"
            ).fetchone()
            min_date, max_date = row[0], row[1]
        else:
            self._warnings.append(f"date_column_unknown:{table}")

        ticker_count: int | None = None
        if "ticker" in columns:
            ticker_count = conn.execute(f"SELECT COUNT(DISTINCT ticker) FROM {table}").fetchone()[0]

        duplicate_key_count: int | None = None
        if spec.identity_columns and all(col in columns for col in spec.identity_columns):
            group_cols = ", ".join(spec.identity_columns)
            row = conn.execute(f"""
                SELECT COALESCE(SUM(cnt - 1), 0) FROM (
                    SELECT COUNT(*) AS cnt FROM {table} GROUP BY {group_cols}
                ) dup WHERE cnt > 1
                """).fetchone()
            duplicate_key_count = row[0]
        else:
            self._warnings.append(f"duplicate_key_unknown:{table}")

        null_summary: dict[str, int] = {}
        candidate_null_columns = {"ticker", spec.date_column, "source"} & columns
        for column in sorted(c for c in candidate_null_columns if c):
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
            ).fetchone()[0]
            null_summary[column] = null_count

        return AuditTableSummary(
            table=table,
            row_count=row_count,
            min_date=min_date,
            max_date=max_date,
            ticker_count=ticker_count,
            duplicate_key_count=duplicate_key_count,
            null_summary=null_summary,
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
