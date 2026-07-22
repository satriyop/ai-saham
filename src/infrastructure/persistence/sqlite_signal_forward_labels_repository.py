"""SQLite repository for deterministic signal forward labels."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from src.domain.value_objects.signal_artifact_schema import (
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
    validate_route_metadata_identity,
    validate_flow_component_fingerprint,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner
from src.infrastructure.persistence.sqlite_signal_artifact_identity_codec import (
    decode_signal_artifact_identity,
    encode_signal_artifact_identity,
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS signal_forward_labels (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                   TEXT    NOT NULL,
    signal_date              TEXT    NOT NULL,
    horizon                  TEXT    NOT NULL,
    observation_captured_at  TEXT    NOT NULL DEFAULT '',
    entry_reference_price    TEXT,
    label_window_start       TEXT,
    label_window_end         TEXT,
    close_return             REAL,
    max_forward_return       REAL,
    max_adverse_excursion    REAL,
    days_to_peak             INTEGER,
    days_to_trough           INTEGER,
    stop_would_trigger       INTEGER,
    target_would_trigger     INTEGER,
    outcome_label            TEXT    NOT NULL,
    unavailable_reason       TEXT,
    fingerprint_json         TEXT    NOT NULL,
    schema_version           INTEGER NOT NULL DEFAULT 1,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    UNIQUE(ticker, signal_date, horizon, observation_captured_at)
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_signal_forward_labels_ticker_date
ON signal_forward_labels(ticker, signal_date, horizon)
"""

# Effective-session provenance columns (DQ-002E). Metadata only — the unique
# identity constraint above (ticker, signal_date, horizon,
# observation_captured_at) is unchanged. Legacy rows predate this migration
# and default to '' (text) / NULL (is_eod_pending), reading back as None.
_ADD_DECISION_AT_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN decision_at TEXT NOT NULL DEFAULT ''
"""
_ADD_LATEST_COMPLETED_SESSION_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN latest_completed_session TEXT NOT NULL DEFAULT ''
"""
_ADD_ANALYSIS_AS_OF_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN analysis_as_of TEXT NOT NULL DEFAULT ''
"""
_ADD_MARKET_SESSION_NAME_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN market_session_name TEXT NOT NULL DEFAULT ''
"""
_ADD_IS_EOD_PENDING_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN is_eod_pending INTEGER
"""
_ADD_RESOLUTION_SOURCE_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN resolution_source TEXT NOT NULL DEFAULT ''
"""
_ADD_RESOLUTION_NOTES_JSON_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN resolution_notes_json TEXT NOT NULL DEFAULT '[]'
"""

# ARTIFACT-IDENTITY Slice 4: pre-resolved artifact identity columns.
# All three are TEXT NOT NULL DEFAULT ''. Empty strings decode as None;
# partial non-empty values fail on read.
_ADD_ARTIFACT_ID_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN artifact_id TEXT NOT NULL DEFAULT ''
"""
_ADD_SEMANTIC_COMPATIBILITY_ID_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN semantic_compatibility_id TEXT NOT NULL DEFAULT ''
"""
_ADD_ARTIFACT_PROVENANCE_JSON_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN artifact_provenance_json TEXT NOT NULL DEFAULT ''
"""

# DQ-004 follow-up: durable raw-vs-executable marker. Additive; legacy rows
# default to 'raw_market' so round-trips no longer silently invent the field.
_ADD_OUTCOME_BASIS_COLUMN = """
ALTER TABLE signal_forward_labels ADD COLUMN outcome_basis TEXT NOT NULL DEFAULT 'raw_market'
"""

# DQ-002 criterion 3: a canonical forward label must carry execution-time +
# effective-session provenance. Labels have no data_as_of_date column of their
# own — their data cutoff is the observation's latest_completed_session,
# inherited verbatim via observation_captured_at + the session fields. Rows
# missing any of these are excluded from list(), the canonical bulk read used
# by summary/readiness aggregates. Point lookups (get, get_at) remain
# permissive so diagnostic paths can still inspect non-canonical rows.
_LABEL_CANONICAL_PROVENANCE_PREDICATES = (
    "decision_at != '' "
    "AND latest_completed_session != '' "
    "AND analysis_as_of != '' "
    "AND observation_captured_at != ''"
)


class SQLiteSignalForwardLabelsRepository:
    """Persists schema-versioned signal_forward_labels records."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        runner = SqliteMigrationRunner(self._db_path)
        runner.run(
            "signal_forward_labels",
            [
                (0, _CREATE_TABLE),
                (1, _CREATE_INDEX),
                (2, _ADD_DECISION_AT_COLUMN),
                (3, _ADD_LATEST_COMPLETED_SESSION_COLUMN),
                (4, _ADD_ANALYSIS_AS_OF_COLUMN),
                (5, _ADD_MARKET_SESSION_NAME_COLUMN),
                (6, _ADD_IS_EOD_PENDING_COLUMN),
                (7, _ADD_RESOLUTION_SOURCE_COLUMN),
                (8, _ADD_RESOLUTION_NOTES_JSON_COLUMN),
                (9, _ADD_ARTIFACT_ID_COLUMN),
                (10, _ADD_SEMANTIC_COMPATIBILITY_ID_COLUMN),
                (11, _ADD_ARTIFACT_PROVENANCE_JSON_COLUMN),
                (12, _ADD_OUTCOME_BASIS_COLUMN),
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_many(self, labels: list[SignalForwardLabel]) -> None:
        if not labels:
            return
        now = datetime.now(UTC).isoformat()
        rows = []
        for label in labels:
            # SECTOR-CONTEXT-IDENTITY defense-in-depth: never persist a current
            # label carrying the removed market_context Alpha/Trigger identity.
            if label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION:
                validate_route_metadata_identity(
                    label.fingerprint.alpha_trigger_route_metadata,
                    context="signal forward label write",
                )
                validate_flow_component_fingerprint(
                    component_coverage=label.fingerprint.flow_component_coverage,
                    missing_components=label.fingerprint.flow_missing_components,
                    context="signal forward label write",
                )
            artifact_id_str, sem_compat_id_str, provenance_json = (
                encode_signal_artifact_identity(label.artifact_identity)
            )
            rows.append(
                (
                    label.ticker.upper(),
                    label.signal_date.isoformat(),
                    label.horizon.value,
                    (
                        label.observation_captured_at.isoformat()
                        if label.observation_captured_at
                        else ""
                    ),
                    (
                        str(label.entry_reference_price)
                        if label.entry_reference_price is not None
                        else None
                    ),
                    (label.label_window_start.isoformat() if label.label_window_start else None),
                    label.label_window_end.isoformat() if label.label_window_end else None,
                    label.close_return,
                    label.max_forward_return,
                    label.max_adverse_excursion,
                    label.days_to_peak,
                    label.days_to_trough,
                    _bool_to_db(label.stop_would_trigger),
                    _bool_to_db(label.target_would_trigger),
                    label.outcome_label.value,
                    label.unavailable_reason,
                    json.dumps(
                        label.fingerprint_payload(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    label.schema_version,
                    now,
                    now,
                    label.decision_at.isoformat() if label.decision_at else "",
                    (
                        label.latest_completed_session.isoformat()
                        if label.latest_completed_session
                        else ""
                    ),
                    label.analysis_as_of.isoformat() if label.analysis_as_of else "",
                    label.market_session_name or "",
                    _bool_to_db(label.is_eod_pending),
                    label.resolution_source or "",
                    json.dumps(list(label.resolution_notes), separators=(",", ":")),
                    artifact_id_str,
                    sem_compat_id_str,
                    provenance_json,
                    label.outcome_basis or "raw_market",
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signal_forward_labels
                    (ticker, signal_date, horizon, observation_captured_at,
                     entry_reference_price, label_window_start, label_window_end,
                     close_return, max_forward_return, max_adverse_excursion,
                     days_to_peak, days_to_trough, stop_would_trigger,
                     target_would_trigger, outcome_label, unavailable_reason,
                     fingerprint_json, schema_version, created_at, updated_at,
                     decision_at, latest_completed_session, analysis_as_of,
                     market_session_name, is_eod_pending, resolution_source,
                     resolution_notes_json,
                     artifact_id, semantic_compatibility_id, artifact_provenance_json,
                     outcome_basis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, signal_date, horizon, observation_captured_at)
                DO UPDATE SET
                    entry_reference_price = excluded.entry_reference_price,
                    label_window_start = excluded.label_window_start,
                    label_window_end = excluded.label_window_end,
                    close_return = excluded.close_return,
                    max_forward_return = excluded.max_forward_return,
                    max_adverse_excursion = excluded.max_adverse_excursion,
                    days_to_peak = excluded.days_to_peak,
                    days_to_trough = excluded.days_to_trough,
                    stop_would_trigger = excluded.stop_would_trigger,
                    target_would_trigger = excluded.target_would_trigger,
                    outcome_label = excluded.outcome_label,
                    unavailable_reason = excluded.unavailable_reason,
                    fingerprint_json = excluded.fingerprint_json,
                    schema_version = excluded.schema_version,
                    updated_at = excluded.updated_at,
                    decision_at = excluded.decision_at,
                    latest_completed_session = excluded.latest_completed_session,
                    analysis_as_of = excluded.analysis_as_of,
                    market_session_name = excluded.market_session_name,
                    is_eod_pending = excluded.is_eod_pending,
                    resolution_source = excluded.resolution_source,
                    resolution_notes_json = excluded.resolution_notes_json,
                    artifact_id = excluded.artifact_id,
                    semantic_compatibility_id = excluded.semantic_compatibility_id,
                    artifact_provenance_json = excluded.artifact_provenance_json,
                    outcome_basis = excluded.outcome_basis
                """,
                rows,
            )

    def get(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
    ) -> SignalForwardLabel | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signal_forward_labels
                WHERE ticker = ? AND signal_date = ? AND horizon = ?
                ORDER BY observation_captured_at DESC, id DESC
                LIMIT 1
                """,
                (ticker.upper(), signal_date.isoformat(), horizon.value),
            ).fetchone()
        return _row_to_label(row) if row else None

    def get_at(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
        observation_captured_at: datetime,
    ) -> SignalForwardLabel | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signal_forward_labels
                WHERE ticker = ?
                  AND signal_date = ?
                  AND horizon = ?
                  AND observation_captured_at = ?
                LIMIT 1
                """,
                (
                    ticker.upper(),
                    signal_date.isoformat(),
                    horizon.value,
                    observation_captured_at.isoformat(),
                ),
            ).fetchone()
        return _row_to_label(row) if row else None

    def list(
        self,
        *,
        signal_date: date | None = None,
        horizon: SignalLabelHorizon | None = None,
        ticker: str | None = None,
    ) -> list[SignalForwardLabel]:
        """Bulk canonical read for forward labels.

        DQ-002 criterion 3: returns only current-schema labels that carry
        full effective-session + execution-time provenance (decision_at,
        latest_completed_session, analysis_as_of, observation_captured_at).
        Legacy-schema or provenance-missing rows drop from this read;
        point lookups (get, get_at) remain permissive for diagnostics.
        """
        clauses: list[str] = [
            "schema_version = ?",
            _LABEL_CANONICAL_PROVENANCE_PREDICATES,
        ]
        params: list[str | int] = [SIGNAL_FORWARD_LABEL_SCHEMA_VERSION]
        if signal_date is not None:
            clauses.append("signal_date = ?")
            params.append(signal_date.isoformat())
        if horizon is not None:
            clauses.append("horizon = ?")
            params.append(horizon.value)
        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        where = f"WHERE {' AND '.join(clauses)}"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM signal_forward_labels
                {where}
                ORDER BY signal_date DESC, ticker ASC, horizon ASC, observation_captured_at DESC
                """,
                params,
            ).fetchall()
        return [_row_to_label(row) for row in rows]


def _row_to_label(row: sqlite3.Row) -> SignalForwardLabel:
    schema_version = int(row["schema_version"])
    if schema_version > SIGNAL_FORWARD_LABEL_SCHEMA_VERSION:
        raise ValueError(f"Unsupported signal forward label schema_version={schema_version}")
    fingerprint_data = json.loads(row["fingerprint_json"])
    # SECTOR-CONTEXT-IDENTITY defense-in-depth: reject a raw-inserted current
    # label carrying the removed market_context identity before it is decoded
    # into a canonical label (readers must not trust stored payload contents).
    if schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION:
        validate_route_metadata_identity(
            (fingerprint_data or {}).get("alpha_trigger_route_metadata"),
            context="signal forward label read",
        )
        validate_flow_component_fingerprint(
            component_coverage=(fingerprint_data or {}).get("flow_component_coverage"),
            missing_components=(fingerprint_data or {}).get("flow_missing_components"),
            context="signal forward label read",
        )
    return SignalForwardLabel(
        ticker=row["ticker"],
        signal_date=date.fromisoformat(row["signal_date"]),
        horizon=SignalLabelHorizon(row["horizon"]),
        entry_reference_price=(
            None
            if row["entry_reference_price"] is None
            else Decimal(str(row["entry_reference_price"]))
        ),
        label_window_start=_date_or_none(row["label_window_start"]),
        label_window_end=_date_or_none(row["label_window_end"]),
        close_return=row["close_return"],
        max_forward_return=row["max_forward_return"],
        max_adverse_excursion=row["max_adverse_excursion"],
        days_to_peak=row["days_to_peak"],
        days_to_trough=row["days_to_trough"],
        stop_would_trigger=_bool_from_db(row["stop_would_trigger"]),
        target_would_trigger=_bool_from_db(row["target_would_trigger"]),
        outcome_label=SignalForwardOutcome(row["outcome_label"]),
        unavailable_reason=row["unavailable_reason"],
        fingerprint=SignalObservationFingerprint.from_dict(fingerprint_data),
        observation_captured_at=(
            datetime.fromisoformat(row["observation_captured_at"])
            if row["observation_captured_at"]
            else None
        ),
        outcome_basis=str(row["outcome_basis"] or "raw_market"),
        decision_at=(
            datetime.fromisoformat(row["decision_at"]) if row["decision_at"] else None
        ),
        latest_completed_session=_date_or_none(row["latest_completed_session"]),
        analysis_as_of=_date_or_none(row["analysis_as_of"]),
        market_session_name=row["market_session_name"] or None,
        is_eod_pending=_bool_from_db(row["is_eod_pending"]),
        resolution_source=row["resolution_source"] or None,
        resolution_notes=_resolution_notes_from_db(row["resolution_notes_json"]),
        schema_version=schema_version,
        artifact_identity=decode_signal_artifact_identity(
            artifact_id_raw=row["artifact_id"],
            semantic_compatibility_id_raw=row["semantic_compatibility_id"],
            provenance_json_raw=row["artifact_provenance_json"],
        ),
    )


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _bool_from_db(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _resolution_notes_from_db(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed)
