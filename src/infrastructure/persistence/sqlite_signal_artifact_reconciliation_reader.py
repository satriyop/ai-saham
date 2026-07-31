"""
Read-only SQLite observer for the DQ-001E signal-artifact/market-context
reconciliation audit.

Canonical learning plane (post clean-break):
  learning_observations, learning_outcome_labels,
  market_context_snapshots, regime_observations.

Retired tables candidate_observations / signal_forward_labels are not required
and are not observed here.

Opens SQLite in read-only URI mode and never executes write/DDL statements.
Uses SQL aggregate queries only — never loads full tables into Python.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from src.application.dto.source_reconciliation_dto import (
    RawCandidateObservationIdentityObservation,
    RawLearningObservationsRiskPitObservation,
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

# Post clean-break SSOT (learning plane). DTO field names still say
# "canonical"/"legacy" for config_hash-era semantics: here they map to
# compatibility_id present vs blank.
_LEARNING_OBSERVATIONS_IDENTITY_REQUIRED_COLUMNS = (
    "observation_id",
    "purpose",
    "compatibility_id",
    "captured_at",
    "decision_payload_json",
    "contract_id",
    "window_id",
)
_LEARNING_OUTCOME_LABELS_REQUIRED_COLUMNS = (
    "label_id",
    "observation_id",
    "contract_id",
    "metrics_json",
)
_LEARNING_OBSERVATIONS_LINKAGE_COLUMNS = ("observation_id",)
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
_LEARNING_OBSERVATIONS_REQUIRED_COLUMNS = (
    "purpose",
    "decision_payload_json",
)
_ACCUMULATION_DISCOVERY_PURPOSE = "ACCUMULATION_DISCOVERY"


class SQLiteSignalArtifactReconciliationReader:
    """Read-only observer of signal-artifact/market-context reconciliation facts (DQ-001E)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation:
        """Observe learning_observations identity (canonical post clean-break).

        Method name kept for call-site stability; table is learning_observations.
        DTO ``canonical_*`` = rows with non-empty compatibility_id;
        ``legacy_*`` = blank/null compatibility_id.
        """
        table = "learning_observations"
        if not self._db_path.exists():
            return RawCandidateObservationIdentityObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawCandidateObservationIdentityObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(
                columns, _LEARNING_OBSERVATIONS_IDENTITY_REQUIRED_COLUMNS
            )
            if missing:
                return RawCandidateObservationIdentityObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            canonical_row_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE compatibility_id IS NOT NULL AND TRIM(compatibility_id) != ''"
            ).fetchone()[0]
            legacy_row_count = row_count - canonical_row_count

            canonical_missing_condition = (
                "compatibility_id IS NOT NULL AND TRIM(compatibility_id) != '' AND ("
                "observation_id IS NULL OR observation_id = '' OR "
                "purpose IS NULL OR purpose = '' OR "
                "captured_at IS NULL OR captured_at = '' OR "
                "contract_id IS NULL OR contract_id = '' OR "
                "window_id IS NULL OR window_id = '' OR "
                "decision_payload_json IS NULL OR decision_payload_json = ''"
                ")"
            )
            canonical_missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {canonical_missing_condition}"
            ).fetchone()[0]
            canonical_missing_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT observation_id, purpose, captured_at, contract_id, window_id, "
                f"compatibility_id FROM {table} WHERE {canonical_missing_condition} "
                f"LIMIT {_MAX_SAMPLE_ROWS}",
            )

            duplicate_canonical_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} "
                "WHERE compatibility_id IS NOT NULL AND TRIM(compatibility_id) != '' "
                "AND observation_id IS NOT NULL AND observation_id != '' "
                "GROUP BY observation_id HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_canonical_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT observation_id, COUNT(*) AS duplicate_row_count "
                f"FROM {table} "
                "WHERE compatibility_id IS NOT NULL AND TRIM(compatibility_id) != '' "
                "AND observation_id IS NOT NULL AND observation_id != '' "
                "GROUP BY observation_id "
                f"HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_payload_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(decision_payload_json) = 0"
            ).fetchone()[0]
            invalid_payload_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT observation_id, purpose, captured_at FROM {table} "
                f"WHERE json_valid(decision_payload_json) = 0 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            payload_missing_marker_condition = (
                "json_valid(decision_payload_json) = 1 "
                "AND json_extract(decision_payload_json, '$.schema_version') IS NULL"
            )
            payload_missing_schema_marker_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {payload_missing_marker_condition}"
            ).fetchone()[0]
            payload_missing_schema_marker_samples = self._rows_as_dicts(
                conn,
                f"SELECT observation_id, purpose, captured_at FROM {table} "
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
        """Observe learning_outcome_labels identity + join to learning_observations.

        Method name kept for call-site stability; table is learning_outcome_labels.
        Fingerprint check uses metrics_json (canonical path metrics payload).
        """
        table = "learning_outcome_labels"
        if not self._db_path.exists():
            return RawSignalForwardLabelsLinkageObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawSignalForwardLabelsLinkageObservation(exists=False)

            columns = self._columns(conn, table)
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            missing = self._missing_columns(columns, _LEARNING_OUTCOME_LABELS_REQUIRED_COLUMNS)
            if missing:
                return RawSignalForwardLabelsLinkageObservation(
                    exists=True,
                    row_count=row_count,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            missing_identity_condition = (
                "(label_id IS NULL OR label_id = '' OR "
                "observation_id IS NULL OR observation_id = '' OR "
                "contract_id IS NULL OR contract_id = '')"
            )
            missing_identity_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {missing_identity_condition}"
            ).fetchone()[0]
            missing_identity_samples = self._rows_as_dicts(
                conn,
                f"SELECT label_id, observation_id, contract_id FROM {table} "
                f"WHERE {missing_identity_condition} LIMIT {_MAX_SAMPLE_ROWS}",
            )

            non_null_identity = (
                "label_id IS NOT NULL AND label_id != '' AND "
                "observation_id IS NOT NULL AND observation_id != '' AND "
                "contract_id IS NOT NULL AND contract_id != ''"
            )
            duplicate_identity_count = conn.execute(
                f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
                f"SELECT COUNT(*) AS cnt FROM {table} WHERE {non_null_identity} "
                "GROUP BY observation_id, contract_id HAVING cnt > 1"
                ")"
            ).fetchone()[0]
            duplicate_identity_samples = self._rows_as_dicts(
                conn,
                "SELECT observation_id, contract_id, "
                f"COUNT(*) AS duplicate_row_count FROM {table} WHERE {non_null_identity} "
                "GROUP BY observation_id, contract_id "
                f"HAVING COUNT(*) > 1 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            invalid_fingerprint_json_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE json_valid(metrics_json) = 0"
            ).fetchone()[0]
            invalid_fingerprint_json_samples = self._rows_as_dicts(
                conn,
                f"SELECT label_id, observation_id, contract_id FROM {table} "
                f"WHERE json_valid(metrics_json) = 0 LIMIT {_MAX_SAMPLE_ROWS}",
            )

            linkage_provable = self._table_exists(
                conn, "learning_observations"
            ) and not self._missing_columns(
                self._columns(conn, "learning_observations"),
                _LEARNING_OBSERVATIONS_LINKAGE_COLUMNS,
            )

            orphan_linkage_count = 0
            orphan_linkage_samples: tuple[dict, ...] = ()
            if linkage_provable:
                orphan_where = (
                    "o.observation_id IS NULL AND l.observation_id IS NOT NULL "
                    "AND l.observation_id != ''"
                )
                orphan_linkage_count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} l "
                    "LEFT JOIN learning_observations o "
                    "ON o.observation_id = l.observation_id "
                    f"WHERE {orphan_where}"
                ).fetchone()[0]
                orphan_linkage_samples = self._rows_as_dicts(
                    conn,
                    "SELECT l.label_id AS label_id, l.observation_id AS observation_id, "
                    "l.contract_id AS contract_id "
                    f"FROM {table} l LEFT JOIN learning_observations o "
                    "ON o.observation_id = l.observation_id "
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

            missing = self._missing_columns(columns, _MARKET_CONTEXT_SNAPSHOT_REQUIRED_COLUMNS)
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
                f"SELECT as_of_date FROM {table} WHERE created_at IS NULL LIMIT {_MAX_SAMPLE_ROWS}",
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

    def observe_learning_observations_risk_pit(
        self,
    ) -> RawLearningObservationsRiskPitObservation:
        """ACCUMULATION_DISCOVERY risk.snapshot_date vs session_date (PIT).

        Uses purpose-filtered row load + Python classification rather than pure
        SQL aggregates: risk lives under a dynamic features_by_window key
        (canonical_window), and edge cases (missing risk, unreadable JSON)
        are clearer and less brittle in Python for this small table.
        """
        table = "learning_observations"
        if not self._db_path.exists():
            return RawLearningObservationsRiskPitObservation(exists=False)

        with closing(self._connect()) as conn:
            if not self._table_exists(conn, table):
                return RawLearningObservationsRiskPitObservation(exists=False)

            columns = self._columns(conn, table)
            missing = self._missing_columns(columns, _LEARNING_OBSERVATIONS_REQUIRED_COLUMNS)
            if missing:
                total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                return RawLearningObservationsRiskPitObservation(
                    exists=True,
                    row_count=total,
                    schema_sufficient=False,
                    missing_columns=missing,
                )

            rows = conn.execute(
                f"SELECT decision_payload_json FROM {table} WHERE purpose = ?",
                (_ACCUMULATION_DISCOVERY_PURPOSE,),
            ).fetchall()

        return _classify_learning_observations_risk_pit(
            payloads=[row[0] for row in rows],
            sample_cap=_MAX_SAMPLE_ROWS,
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


def _parse_iso_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text[:10])
        return date.fromisoformat(text)
    except ValueError:
        return None


def _classify_learning_observations_risk_pit(
    *,
    payloads: list[object],
    sample_cap: int,
) -> RawLearningObservationsRiskPitObservation:
    """Classify ACCUMULATION_DISCOVERY payloads for risk PIT coherence."""
    after_count = 0
    after_samples: list[dict] = []
    mismatch_count = 0
    mismatch_samples: list[dict] = []
    unreadable_count = 0
    unreadable_samples: list[dict] = []

    def _push(samples: list[dict], row: dict) -> None:
        if len(samples) < sample_cap:
            samples.append(row)

    for raw_payload in payloads:
        ticker = ""
        session_raw: str | None = None

        if not isinstance(raw_payload, str):
            unreadable_count += 1
            _push(
                unreadable_samples,
                {"ticker": ticker, "session_date": None, "risk_snapshot_date": None},
            )
            continue

        try:
            payload = json.loads(raw_payload)
        except (TypeError, json.JSONDecodeError):
            unreadable_count += 1
            _push(
                unreadable_samples,
                {"ticker": ticker, "session_date": None, "risk_snapshot_date": None},
            )
            continue

        if not isinstance(payload, dict):
            unreadable_count += 1
            _push(
                unreadable_samples,
                {"ticker": ticker, "session_date": None, "risk_snapshot_date": None},
            )
            continue

        ticker = str(payload.get("ticker") or "")
        session_raw = payload.get("session_date")
        if session_raw is not None and not isinstance(session_raw, str):
            session_raw = str(session_raw)
        session_date = _parse_iso_date(session_raw)
        if session_date is None:
            unreadable_count += 1
            _push(
                unreadable_samples,
                {
                    "ticker": ticker,
                    "session_date": session_raw if isinstance(session_raw, str) else None,
                    "risk_snapshot_date": None,
                },
            )
            continue

        if "canonical_window" in payload and payload["canonical_window"] is not None:
            window_key = str(payload["canonical_window"])
        else:
            window_key = "7"

        features = payload.get("features_by_window")
        if not isinstance(features, dict):
            features = {}
        window_pack = features.get(window_key)
        if not isinstance(window_pack, dict):
            continue

        if "risk" not in window_pack:
            continue
        risk = window_pack.get("risk")
        if risk is None:
            continue
        if not isinstance(risk, dict):
            unreadable_count += 1
            _push(
                unreadable_samples,
                {
                    "ticker": ticker,
                    "session_date": session_date.isoformat(),
                    "risk_snapshot_date": None,
                },
            )
            continue

        row_unreadable = False
        risk_snap_raw = risk.get("snapshot_date")
        if risk_snap_raw is not None and not isinstance(risk_snap_raw, str):
            risk_snap_raw = str(risk_snap_raw)
        risk_snap = _parse_iso_date(risk_snap_raw)
        if risk_snap is None:
            row_unreadable = True
            unreadable_count += 1
            _push(
                unreadable_samples,
                {
                    "ticker": ticker,
                    "session_date": session_date.isoformat(),
                    "risk_snapshot_date": risk_snap_raw if isinstance(risk_snap_raw, str) else None,
                },
            )
        elif risk_snap > session_date:
            after_count += 1
            _push(
                after_samples,
                {
                    "ticker": ticker,
                    "session_date": session_date.isoformat(),
                    "risk_snapshot_date": risk_snap.isoformat(),
                },
            )

        gate_ctx = risk.get("gate_context")
        if isinstance(gate_ctx, dict):
            gate_raw = gate_ctx.get("snapshot_date")
            if gate_raw is not None and not isinstance(gate_raw, str):
                gate_raw = str(gate_raw)
            gate_snap = _parse_iso_date(gate_raw)
            if gate_snap is None:
                if not row_unreadable:
                    unreadable_count += 1
                    _push(
                        unreadable_samples,
                        {
                            "ticker": ticker,
                            "session_date": session_date.isoformat(),
                            "risk_snapshot_date": risk_snap.isoformat() if risk_snap else None,
                            "gate_context_snapshot_date": gate_raw
                            if isinstance(gate_raw, str)
                            else None,
                        },
                    )
            elif gate_snap != session_date:
                mismatch_count += 1
                _push(
                    mismatch_samples,
                    {
                        "ticker": ticker,
                        "session_date": session_date.isoformat(),
                        "risk_snapshot_date": risk_snap.isoformat() if risk_snap else None,
                        "gate_context_snapshot_date": gate_snap.isoformat(),
                    },
                )

    return RawLearningObservationsRiskPitObservation(
        exists=True,
        row_count=len(payloads),
        risk_snapshot_after_session_count=after_count,
        risk_snapshot_after_session_samples=tuple(after_samples),
        gate_context_session_mismatch_count=mismatch_count,
        gate_context_session_mismatch_samples=tuple(mismatch_samples),
        risk_snapshot_unreadable_count=unreadable_count,
        risk_snapshot_unreadable_samples=tuple(unreadable_samples),
    )
