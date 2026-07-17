"""
Read-only SQLite observer for the DQ-001E signal-artifact/market-context
reconciliation audit (candidate_observations, signal_forward_labels,
market_context_snapshots, regime_observations).

Opens SQLite in read-only URI mode and never executes write/DDL statements.
Uses SQL aggregate queries only — never loads full tables into Python.
Sibling to sqlite_source_reconciliation_reader.py (DQ-001B core tables) and
sqlite_enrichment_reconciliation_reader.py (DQ-001D enrichment tables); kept
separate per table-family so no single reader module grows past the
AI_AGENT_CHECKLIST.md repository-module size guidance.

Every observer checks required columns via PRAGMA table_info before
querying them. A table that exists but is missing a required column
returns exists=True, schema_sufficient=False, and the missing column
names — never a crash.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from src.application.dto.source_reconciliation_dto import (
    RawCandidateObservationIdentityObservation,
    RawMarketContextSnapshotObservation,
    RawRegimeObservationsObservation,
    RawSignalForwardLabelsLinkageObservation,
)
from src.domain.value_objects.market_context import MarketRegime

_MAX_SAMPLE_ROWS = 10

# Both market_context_snapshots.regime and regime_observations.regime store
# MarketRegime.value (see sqlite_market_context_repository.py / row["regime"]
# and RegimeDetectionEvidence.regime: str # MarketRegime.value). A regime
# value outside this set is invalid, not just null/empty/"unknown".
_VALID_REGIME_VALUES = tuple(m.value for m in MarketRegime)
# Enum values are fixed Python literals (A-Z/underscore only, never external
# input), so embedding them directly as quoted SQL literals is safe and lets
# this condition be reused by both the count query and the _rows_as_dicts
# sample query (which does not support bound parameters).
_INVALID_REGIME_CONDITION = "(regime IS NULL OR regime = '' OR upper(regime) NOT IN ({}))".format(
    ", ".join(f"'{v.upper()}'" for v in _VALID_REGIME_VALUES)
)

_CANDIDATE_OBSERVATIONS_REQUIRED_COLUMNS = (
    "ticker",
    "snapshot_date",
    "captured_at",
    "workflow",
    "window_sessions",
    "data_as_of_date",
    "config_hash",
    "payload_json",
)
_SIGNAL_FORWARD_LABELS_REQUIRED_COLUMNS = (
    "ticker",
    "signal_date",
    "horizon",
    "observation_captured_at",
    "fingerprint_json",
)
_CANDIDATE_OBSERVATIONS_LINKAGE_COLUMNS = ("ticker", "snapshot_date", "captured_at")
_MARKET_CONTEXT_SNAPSHOT_REQUIRED_COLUMNS = (
    "as_of_date",
    "regime",
    "created_at",
    "factors_json",
)
_REGIME_OBSERVATIONS_REQUIRED_COLUMNS = (
    "observation_date",
    "regime",
    "regime_confidence",
    "regime_stability",
    "detection_inputs_json",
)


class SQLiteSignalArtifactReconciliationReader:
    """Read-only observer of signal-artifact/market-context reconciliation facts (DQ-001E)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation:
        table = "candidate_observations"
        if not self._db_path.exists():
            return RawCandidateObservationIdentityObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawCandidateObservationIdentityObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _CANDIDATE_OBSERVATIONS_REQUIRED_COLUMNS)
            if missing:
                return RawCandidateObservationIdentityObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            canonical_row_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE config_hash != '' AND schema_version = 2"
            ).fetchone()[0]
            legacy_row_count = row_count - canonical_row_count

            canonical_missing_condition = (
                "config_hash != '' AND schema_version = 2 AND ("
                "ticker IS NULL OR ticker = '' OR "
                "snapshot_date IS NULL OR snapshot_date = '' OR "
                "captured_at IS NULL OR captured_at = '' OR "
                "workflow IS NULL OR workflow = '' OR "
                "data_as_of_date IS NULL OR data_as_of_date = '' OR "
                "window_sessions IS NULL OR window_sessions <= 0"
                ")"
            )
            canonical_missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {canonical_missing_condition}"
            ).fetchone()[0]
            canonical_missing_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, snapshot_date, captured_at, workflow, window_sessions, "
                f"data_as_of_date FROM {table} WHERE {canonical_missing_condition} "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_canonical_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} WHERE config_hash != '' AND schema_version = 2 "
                "GROUP BY ticker, snapshot_date, workflow, window_sessions, "
                "data_as_of_date, config_hash HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_canonical_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, snapshot_date, workflow, window_sessions, data_as_of_date, "
                f"config_hash, COUNT(*) AS duplicate_row_count FROM {table} "
                "WHERE config_hash != '' AND schema_version = 2 GROUP BY ticker, snapshot_date, workflow, "
                "window_sessions, data_as_of_date, config_hash "
                f"HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_payload_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(payload_json) = 0"
            ).fetchone()[0]
            invalid_payload_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, snapshot_date, captured_at FROM {table} "
                f"WHERE json_valid(payload_json) = 0 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            payload_missing_marker_condition = (
                "json_valid(payload_json) = 1 "
                "AND json_extract(payload_json, '$.schema_version') IS NULL"
            )
            payload_missing_schema_marker_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {payload_missing_marker_condition}"
            ).fetchone()[0]
            payload_missing_schema_marker_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, snapshot_date, captured_at FROM {table} "
                f"WHERE {payload_missing_marker_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawCandidateObservationIdentityObservation(
            exists=True,
            row_count=row_count,
            canonical_row_count=canonical_row_count,
            legacy_row_count=legacy_row_count,
            canonical_missing_identity_count=canonical_missing_identity_count,
            canonical_missing_identity_samples=canonical_missing_identity_samples,
            duplicate_canonical_identity_count=duplicate_canonical_identity_count,
            duplicate_canonical_identity_samples=duplicate_canonical_identity_samples,
            invalid_payload_json_count=invalid_payload_json_count,
            invalid_payload_json_samples=invalid_payload_json_samples,
            payload_missing_schema_marker_count=payload_missing_schema_marker_count,
            payload_missing_schema_marker_samples=payload_missing_schema_marker_samples,
        )

    def observe_signal_forward_labels_linkage(
        self,
    ) -> RawSignalForwardLabelsLinkageObservation:
        table = "signal_forward_labels"
        if not self._db_path.exists():
            return RawSignalForwardLabelsLinkageObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawSignalForwardLabelsLinkageObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _SIGNAL_FORWARD_LABELS_REQUIRED_COLUMNS)
            if missing:
                return RawSignalForwardLabelsLinkageObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_identity_condition = (
                "(ticker IS NULL OR ticker = '' OR signal_date IS NULL OR signal_date = '' "
                "OR horizon IS NULL OR horizon = '' OR observation_captured_at IS NULL "
                "OR observation_captured_at = '')"
            )
            missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_identity_condition}"
            ).fetchone()[0]
            missing_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, signal_date, horizon, observation_captured_at FROM {table} "
                f"WHERE {missing_identity_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            non_null_identity = (
                "ticker IS NOT NULL AND ticker != '' AND signal_date IS NOT NULL "
                "AND signal_date != '' AND horizon IS NOT NULL AND horizon != '' "
                "AND observation_captured_at IS NOT NULL AND observation_captured_at != ''"
            )
            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} WHERE {non_null_identity} "
                "GROUP BY ticker, signal_date, horizon, observation_captured_at HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT ticker, signal_date, horizon, observation_captured_at, "
                f"COUNT(*) AS duplicate_row_count FROM {table} WHERE {non_null_identity} "
                "GROUP BY ticker, signal_date, horizon, observation_captured_at "
                f"HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_fingerprint_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(fingerprint_json) = 0"
            ).fetchone()[0]
            invalid_fingerprint_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT ticker, signal_date, horizon FROM {table} "
                f"WHERE json_valid(fingerprint_json) = 0 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            linkage_provable = self._table_exists(
                conn, "candidate_observations"
            ) and not self._missing_columns(
                self._columns(conn, "candidate_observations"),
                _CANDIDATE_OBSERVATIONS_LINKAGE_COLUMNS,
            )

            orphan_linkage_count = 0
            orphan_linkage_samples: tuple[dict, ...] = ()
            if linkage_provable:
                join_condition = (
                    "o.ticker = l.ticker AND o.snapshot_date = l.signal_date "
                    "AND o.captured_at = l.observation_captured_at"
                )
                l_missing_identity_condition = (
                    "(l.ticker IS NULL OR l.ticker = '' OR l.signal_date IS NULL "
                    "OR l.signal_date = '' OR l.horizon IS NULL OR l.horizon = '' "
                    "OR l.observation_captured_at IS NULL OR l.observation_captured_at = '')"
                )
                orphan_where = (
                    f"o.ticker IS NULL AND NOT ({l_missing_identity_condition})"
                )
                orphan_linkage_count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} l "
                    f"LEFT JOIN candidate_observations o ON {join_condition} "
                    f"WHERE {orphan_where}"
                ).fetchone()[0]
                orphan_linkage_samples = self._rows_as_dicts(
                    conn,
                    "SELECT l.ticker AS ticker, l.signal_date AS signal_date, "
                    "l.observation_captured_at AS observation_captured_at "
                    f"FROM {table} l LEFT JOIN candidate_observations o ON {join_condition} "
                    f"WHERE {orphan_where} LIMIT {_MAX_SAMPLE_ROWS}",
                )

        return RawSignalForwardLabelsLinkageObservation(
            exists=True,
            row_count=row_count,
            missing_identity_count=missing_identity_count,
            missing_identity_samples=missing_identity_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            invalid_fingerprint_json_count=invalid_fingerprint_json_count,
            invalid_fingerprint_json_samples=invalid_fingerprint_json_samples,
            linkage_provable=linkage_provable,
            orphan_linkage_count=orphan_linkage_count,
            orphan_linkage_samples=orphan_linkage_samples,
        )

    def observe_market_context_snapshot_identity(
        self,
    ) -> RawMarketContextSnapshotObservation:
        table = "market_context_snapshots"
        if not self._db_path.exists():
            return RawMarketContextSnapshotObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawMarketContextSnapshotObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(
                columns, _MARKET_CONTEXT_SNAPSHOT_REQUIRED_COLUMNS
            )
            if missing:
                return RawMarketContextSnapshotObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            invalid_regime_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {_INVALID_REGIME_CONDITION}"
            ).fetchone()[0]
            invalid_regime_samples = self._rows_as_dicts(
                conn,
                f"SELECT as_of_date, regime FROM {table} "
                f"WHERE {_INVALID_REGIME_CONDITION} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} GROUP BY as_of_date HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT as_of_date, COUNT(*) AS duplicate_row_count FROM {table} "
                f"GROUP BY as_of_date HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            missing_provenance_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE created_at IS NULL"
            ).fetchone()[0]
            missing_provenance_samples = self._rows_as_dicts(
                conn,
                f"SELECT as_of_date FROM {table} WHERE created_at IS NULL "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_factors_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(factors_json) = 0"
            ).fetchone()[0]
            invalid_factors_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT as_of_date FROM {table} WHERE json_valid(factors_json) = 0 "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawMarketContextSnapshotObservation(
            exists=True,
            row_count=row_count,
            invalid_regime_count=invalid_regime_count,
            invalid_regime_samples=invalid_regime_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            missing_provenance_count=missing_provenance_count,
            missing_provenance_samples=missing_provenance_samples,
            invalid_factors_json_count=invalid_factors_json_count,
            invalid_factors_json_samples=invalid_factors_json_samples,
        )

    def observe_regime_observations_identity(self) -> RawRegimeObservationsObservation:
        table = "regime_observations"
        if not self._db_path.exists():
            return RawRegimeObservationsObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawRegimeObservationsObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _REGIME_OBSERVATIONS_REQUIRED_COLUMNS)
            if missing:
                return RawRegimeObservationsObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            invalid_regime_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {_INVALID_REGIME_CONDITION}"
            ).fetchone()[0]
            invalid_regime_samples = self._rows_as_dicts(
                conn,
                f"SELECT observation_date, regime FROM {table} "
                f"WHERE {_INVALID_REGIME_CONDITION} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            null_confidence_or_stability_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE regime_confidence IS NULL "
                "OR regime_stability IS NULL OR regime_stability = ''"
            ).fetchone()[0]

            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} GROUP BY observation_date HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT observation_date, COUNT(*) AS duplicate_row_count FROM {table} "
                f"GROUP BY observation_date HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_detection_inputs_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(detection_inputs_json) = 0"
            ).fetchone()[0]
            invalid_detection_inputs_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT observation_date FROM {table} "
                f"WHERE json_valid(detection_inputs_json) = 0 LIMIT {_MAX_SAMPLE_ROWS}",
            )

        return RawRegimeObservationsObservation(
            exists=True,
            row_count=row_count,
            invalid_regime_count=invalid_regime_count,
            invalid_regime_samples=invalid_regime_samples,
            duplicate_identity_count=duplicate_identity_count,
            duplicate_identity_samples=duplicate_identity_samples,
            null_confidence_or_stability_count=null_confidence_or_stability_count,
            invalid_detection_inputs_json_count=invalid_detection_inputs_json_count,
            invalid_detection_inputs_json_samples=invalid_detection_inputs_json_samples,
        )

    def _missing_columns(
        self, columns: set[str], required: tuple[str, ...]
    ) -> tuple[str, ...]:
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
