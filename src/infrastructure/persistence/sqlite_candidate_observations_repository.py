"""SQLite repository for replayable candidate observations."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    validate_current_alpha_trigger_identity,
    validate_current_flow_component_fingerprint,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner
from src.infrastructure.persistence.sqlite_signal_artifact_identity_codec import (
    decode_signal_artifact_identity,
    encode_signal_artifact_identity,
)

# v1 -> v2 (Task HIGH-1, 2026-07-17): sub_signal_fingerprint replaced the
# ambiguous rs_vs_ihsg_5d_at_signal/rs_vs_ihsg_20d_at_signal fields with typed
# benchmark_excess_return_5_session/20_session evidence.
# v2 -> v3 (Task HIGH-2, 2026-07-17): persists canonical signal_authority_
# coverage and typed setup_readiness_* fields; drops the ambiguous
# coverage_score/conviction_score/phase_strength/phase_coverage_score/
# phase_conviction_score fields. No migration fabricates newer-schema fields
# from older payloads — older rows simply lack them and remain diagnostic-
# readable but non-canonical.
# v3 -> v4 (SECTOR-CONTEXT-IDENTITY): the Alpha/Trigger sector evidence identity
# market_context was removed; SectorContextEvidence emits sector_context.
# Existing schema 1-3 rows are outside the current canonical contract — they
# remain diagnostic-readable and non-canonical, and are not mutated, migrated,
# or reinterpreted (the current-contract validator only inspects schema-4 rows).
_CURRENT_SCHEMA_VERSION = CANDIDATE_OBSERVATION_SCHEMA_VERSION

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS candidate_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT    NOT NULL,
    snapshot_date  TEXT    NOT NULL,
    captured_at    TEXT    NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_json   TEXT    NOT NULL
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_candidate_observations_ticker_date
ON candidate_observations(ticker, snapshot_date, captured_at DESC)
"""

# Canonical identity columns. Existing rows predate this migration and default
# to '' / 0 — they are NOT canonical observations (no config_hash was ever
# computed for them) and stay excluded from the uniqueness constraint below,
# so the migration never fails on pre-existing duplicate ticker/snapshot_date
# rows and old rows remain fully readable via get_latest/list_* as before.
_ADD_IDENTITY_COLUMNS = """
ALTER TABLE candidate_observations ADD COLUMN workflow TEXT NOT NULL DEFAULT ''
"""
_ADD_WINDOW_SESSIONS_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN window_sessions INTEGER NOT NULL DEFAULT 0
"""
_ADD_DATA_AS_OF_DATE_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN data_as_of_date TEXT NOT NULL DEFAULT ''
"""
_ADD_CONFIG_HASH_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN config_hash TEXT NOT NULL DEFAULT ''
"""

# Partial unique index: only rows with a real config_hash (i.e. written by the
# canonical recorder) participate in identity-based uniqueness. Legacy rows
# (config_hash = '') are untouched and cannot collide with canonical rows,
# since canonical writes always carry a non-empty window_sessions/
# data_as_of_date/config_hash.
_CREATE_IDENTITY_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_candidate_observations_identity
ON candidate_observations(
    ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash
)
WHERE config_hash != ''
"""

_IDENTITY_CONFLICT_TARGET = (
    "(ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)"
)

# Effective-session provenance columns (DQ-002E). Metadata only — not part of
# canonical identity above. Legacy rows predate this migration and default to
# '' (text) / NULL (is_eod_pending), which read back as None, matching every
# other legacy-default column in this table.
_ADD_DECISION_AT_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN decision_at TEXT NOT NULL DEFAULT ''
"""
_ADD_LATEST_COMPLETED_SESSION_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN latest_completed_session TEXT NOT NULL DEFAULT ''
"""
_ADD_ANALYSIS_AS_OF_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN analysis_as_of TEXT NOT NULL DEFAULT ''
"""
_ADD_MARKET_SESSION_NAME_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN market_session_name TEXT NOT NULL DEFAULT ''
"""
_ADD_IS_EOD_PENDING_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN is_eod_pending INTEGER
"""
_ADD_RESOLUTION_SOURCE_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN resolution_source TEXT NOT NULL DEFAULT ''
"""
_ADD_RESOLUTION_NOTES_JSON_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN resolution_notes_json TEXT NOT NULL DEFAULT '[]'
"""

# Signal-artifact identity columns (ARTIFACT-IDENTITY Slice 3). Metadata only
# — never part of canonical identity. Legacy/default rows have empty strings,
# which decode as None. No unique index on artifact_id yet.
_ADD_ARTIFACT_ID_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN artifact_id TEXT NOT NULL DEFAULT ''
"""
_ADD_SEMANTIC_COMPATIBILITY_ID_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN semantic_compatibility_id TEXT NOT NULL DEFAULT ''
"""
_ADD_ARTIFACT_PROVENANCE_JSON_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN artifact_provenance_json TEXT NOT NULL DEFAULT ''
"""

# Lean observation identity (DQ-003 Slice A). observation_contract labels the
# canonical contract ("accumulation-discovery"); the whole-config-hash
# semantic_compatibility_id reuses the ARTIFACT-IDENTITY column above but is
# written directly from CandidateObservation.semantic_compatibility_id, NOT via
# the all-three-or-none artifact-identity codec. Legacy/default rows have '',
# which read back as None. Not part of canonical identity.
_ADD_OBSERVATION_CONTRACT_COLUMN = """
ALTER TABLE candidate_observations ADD COLUMN observation_contract TEXT NOT NULL DEFAULT ''
"""

_SELECT_COLUMNS = (
    "ticker, snapshot_date, captured_at, schema_version, payload_json, "
    "workflow, window_sessions, data_as_of_date, config_hash, "
    "decision_at, latest_completed_session, analysis_as_of, market_session_name, "
    "is_eod_pending, resolution_source, resolution_notes_json, "
    "artifact_id, semantic_compatibility_id, artifact_provenance_json, "
    "observation_contract"
)

# DQ-002 criterion 3: a canonical candidate observation must carry
# execution-time + effective-session + data-cutoff provenance. Rows missing
# any of these are excluded from canonical reads regardless of config_hash
# or schema version — provenance is what makes a row reproducible as a
# point-in-time artifact. The canonical identity columns (config_hash,
# schema_version) remain necessary; provenance makes them sufficient.
_CANONICAL_PROVENANCE_PREDICATES = (
    "decision_at != '' "
    "AND latest_completed_session != '' "
    "AND analysis_as_of != '' "
    "AND data_as_of_date != '' "
    # DQ-003 Slice A: a canonical row must carry an explicit observation_contract.
    # A row written without one is not a canonical accumulation-discovery
    # observation, regardless of config_hash/schema/provenance.
    "AND observation_contract != ''"
)


class SQLiteCandidateObservationsRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        runner = SqliteMigrationRunner(self._db_path)
        runner.run(
            "candidate_observations",
            [
                (0, _CREATE_TABLE),
                (1, _CREATE_INDEX),
                (2, _ADD_IDENTITY_COLUMNS),
                (3, _ADD_WINDOW_SESSIONS_COLUMN),
                (4, _ADD_DATA_AS_OF_DATE_COLUMN),
                (5, _ADD_CONFIG_HASH_COLUMN),
                (6, _CREATE_IDENTITY_UNIQUE_INDEX),
                (7, _ADD_DECISION_AT_COLUMN),
                (8, _ADD_LATEST_COMPLETED_SESSION_COLUMN),
                (9, _ADD_ANALYSIS_AS_OF_COLUMN),
                (10, _ADD_MARKET_SESSION_NAME_COLUMN),
                (11, _ADD_IS_EOD_PENDING_COLUMN),
                (12, _ADD_RESOLUTION_SOURCE_COLUMN),
                (13, _ADD_RESOLUTION_NOTES_JSON_COLUMN),
                (14, _ADD_ARTIFACT_ID_COLUMN),
                (15, _ADD_SEMANTIC_COMPATIBILITY_ID_COLUMN),
                (16, _ADD_ARTIFACT_PROVENANCE_JSON_COLUMN),
                (17, _ADD_OBSERVATION_CONTRACT_COLUMN),
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_many(self, observations: list[CandidateObservation]) -> None:
        """Upsert observations by canonical identity.

        Observations with a non-empty config_hash are canonical: a second
        save_many() call with the same (ticker, snapshot_date, workflow,
        window_sessions, data_as_of_date, config_hash) replaces the existing
        row's captured_at/payload rather than appending a duplicate. Callers
        that never set config_hash (none in this codebase) would fall outside
        the partial unique index and simply append, matching legacy behavior.
        """
        if not observations:
            return
        rows = []
        for obs in observations:
            payload = dict(obs.payload)
            schema_version = int(payload.get("schema_version", 1))
            if obs.config_hash != "" and schema_version != _CURRENT_SCHEMA_VERSION:
                raise ValueError(
                    "A non-empty config_hash write requires schema_version == "
                    f"{_CURRENT_SCHEMA_VERSION} (got {schema_version})"
                )
            payload_schema_version = payload.get("schema_version")
            if payload_schema_version is not None and int(payload_schema_version) != schema_version:
                raise ValueError("DB-column and payload schema versions disagree")
            validate_current_alpha_trigger_identity(
                schema_version=schema_version,
                alpha_trigger_route_metadata=(
                    payload.get("sub_signal_fingerprint") or {}
                ).get("alpha_trigger_route_metadata"),
            )
            validate_current_flow_component_fingerprint(
                schema_version=schema_version,
                fingerprint=payload.get("sub_signal_fingerprint") or {},
            )
            artifact_id_str, sem_compat_id_str, provenance_json = (
                encode_signal_artifact_identity(obs.artifact_identity)
            )
            # Lean DQ-003 identity: write the semantic_compatibility_id column
            # from the plain field when present, leaving artifact_id/provenance
            # empty. This deliberately bypasses the all-three-or-none codec —
            # the lean contract persists only the compatibility cohort tag.
            if obs.semantic_compatibility_id is not None:
                sem_compat_id_str = str(obs.semantic_compatibility_id)
            rows.append(
                (
                    obs.ticker.upper(),
                    obs.snapshot_date.isoformat(),
                    obs.captured_at.isoformat(),
                    schema_version,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    obs.workflow,
                    obs.window_sessions,
                    obs.data_as_of_date.isoformat() if obs.data_as_of_date else "",
                    obs.config_hash,
                    obs.decision_at.isoformat() if obs.decision_at else "",
                    (
                        obs.latest_completed_session.isoformat()
                        if obs.latest_completed_session
                        else ""
                    ),
                    obs.analysis_as_of.isoformat() if obs.analysis_as_of else "",
                    obs.market_session_name or "",
                    _bool_to_db(obs.is_eod_pending),
                    obs.resolution_source or "",
                    json.dumps(list(obs.resolution_notes), separators=(",", ":")),
                    artifact_id_str,
                    sem_compat_id_str,
                    provenance_json,
                    obs.observation_contract or "",
                )
            )
        with self._connect() as conn:
            conn.executemany(
                f"""
                INSERT INTO candidate_observations
                    (ticker, snapshot_date, captured_at, schema_version, payload_json,
                     workflow, window_sessions, data_as_of_date, config_hash,
                     decision_at, latest_completed_session, analysis_as_of,
                     market_session_name, is_eod_pending, resolution_source,
                     resolution_notes_json,
                     artifact_id, semantic_compatibility_id, artifact_provenance_json,
                     observation_contract)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT {_IDENTITY_CONFLICT_TARGET} WHERE config_hash != ''
                DO UPDATE SET
                    captured_at = excluded.captured_at,
                    schema_version = excluded.schema_version,
                    payload_json = excluded.payload_json,
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
                    observation_contract = excluded.observation_contract
                """,
                rows,
            )

    def get_latest(self, ticker: str, snapshot_date: date) -> CandidateObservation | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM candidate_observations
                WHERE ticker = ? AND snapshot_date = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (ticker.upper(), snapshot_date.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_observation(row)

    def get_at(
        self,
        ticker: str,
        snapshot_date: date,
        captured_at: datetime,
    ) -> CandidateObservation | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM candidate_observations
                WHERE ticker = ? AND snapshot_date = ? AND captured_at = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ticker.upper(), snapshot_date.isoformat(), captured_at.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_observation(row)

    def list_recent(
        self,
        ticker: str,
        *,
        before_date: date | None = None,
        limit: int = 20,
    ) -> list[CandidateObservation]:
        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM candidate_observations
            WHERE ticker = ?
        """
        params: list[object] = [ticker.upper()]
        if before_date is not None:
            query += " AND snapshot_date < ?"
            params.append(before_date.isoformat())
        query += " ORDER BY snapshot_date DESC, captured_at DESC, id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def list_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return latest saved observation per ticker for a snapshot date."""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM (
                    SELECT
                        {_SELECT_COLUMNS},
                        ROW_NUMBER() OVER (
                            PARTITION BY ticker
                            ORDER BY captured_at DESC, id DESC
                        ) AS row_num
                    FROM candidate_observations
                    WHERE snapshot_date = ?
                )
                WHERE row_num = 1
                ORDER BY ticker ASC
                """,
                (snapshot_date.isoformat(),),
            ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def list_all_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM candidate_observations
                WHERE snapshot_date = ?
                ORDER BY ticker ASC, captured_at DESC, id DESC
                """,
                (snapshot_date.isoformat(),),
            ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def list_canonical_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return every canonical observation for the date — no collapsing.

        Canonical = config_hash != '' and schema_version = _CURRENT_SCHEMA_VERSION
        AND full effective-session + data-cutoff provenance (DQ-002 criterion 3):
        a current-schema row missing decision_at, latest_completed_session,
        analysis_as_of, or data_as_of_date is excluded from canonical reads.

        A ticker with observations across several window_sessions returns one row
        per window, not just the latest.
        """
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM candidate_observations
                WHERE snapshot_date = ?
                  AND config_hash != ''
                  AND schema_version = ?
                  AND {_CANONICAL_PROVENANCE_PREDICATES}
                ORDER BY ticker ASC, window_sessions ASC, data_as_of_date DESC,
                         captured_at DESC, id DESC
                """,
                (snapshot_date.isoformat(), _CURRENT_SCHEMA_VERSION),
            ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def list_snapshot_dates(self) -> list[date]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT snapshot_date
                FROM candidate_observations
                ORDER BY snapshot_date ASC
                """
            ).fetchall()
        return [date.fromisoformat(row["snapshot_date"]) for row in rows]

    def list_canonical_snapshot_dates(self) -> list[date]:
        """Return dates containing at least one canonical observation.

        A date whose only current-schema rows are missing provenance is
        excluded — those rows are not canonical (DQ-002 criterion 3).
        """
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT snapshot_date
                FROM candidate_observations
                WHERE config_hash != ''
                  AND schema_version = ?
                  AND {_CANONICAL_PROVENANCE_PREDICATES}
                ORDER BY snapshot_date ASC
                """,
                (_CURRENT_SCHEMA_VERSION,),
            ).fetchall()
        return [date.fromisoformat(row["snapshot_date"]) for row in rows]

    def list_latest_canonical_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return the latest canonical observation per ticker for the date.

        Canonical filtering (config_hash, schema_version, and DQ-002
        criterion 3 provenance) is applied inside the subquery, before
        ROW_NUMBER() partitions by ticker — a newer legacy or
        provenance-missing row can never displace an older canonical row.
        """
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM (
                    SELECT
                        {_SELECT_COLUMNS},
                        ROW_NUMBER() OVER (
                            PARTITION BY ticker
                            ORDER BY captured_at DESC, id DESC
                        ) AS row_num
                    FROM candidate_observations
                    WHERE snapshot_date = ?
                      AND config_hash != ''
                      AND schema_version = ?
                      AND {_CANONICAL_PROVENANCE_PREDICATES}
                )
                WHERE row_num = 1
                ORDER BY ticker ASC
                """,
                (snapshot_date.isoformat(), _CURRENT_SCHEMA_VERSION),
            ).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def _row_to_observation(self, row: sqlite3.Row) -> CandidateObservation:
        payload = json.loads(row["payload_json"])
        db_schema_version = row["schema_version"]
        payload_schema_version = payload.get("schema_version")
        if payload_schema_version is not None and int(payload_schema_version) != db_schema_version:
            raise ValueError(
                f"DB schema_version ({db_schema_version}) and payload schema_version ({payload_schema_version}) disagree"
            )
        schema_version = int(payload.get("schema_version", db_schema_version))
        if schema_version > _CURRENT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported candidate observation schema_version={schema_version}")
        if schema_version == _CURRENT_SCHEMA_VERSION:
            validate_current_alpha_trigger_identity(
                schema_version=schema_version,
                alpha_trigger_route_metadata=(
                    payload.get("sub_signal_fingerprint") or {}
                ).get("alpha_trigger_route_metadata"),
            )
            validate_current_flow_component_fingerprint(
                schema_version=schema_version,
                fingerprint=payload.get("sub_signal_fingerprint") or {},
            )
        payload.setdefault("schema_version", schema_version)
        data_as_of_date_raw = row["data_as_of_date"]
        # Lean DQ-003 identity vs. full parked artifact identity. A lean row
        # populates ONLY the semantic_compatibility_id column; the all-three-or-
        # none codec would reject that as a partial identity, so detect it and
        # decode the compatibility tag directly. Full-identity rows (all three
        # columns present) still round-trip through the codec.
        artifact_id_raw = row["artifact_id"]
        sem_compat_id_raw = row["semantic_compatibility_id"]
        provenance_json_raw = row["artifact_provenance_json"]
        lean_semantic_compatibility_id = None
        if sem_compat_id_raw and not artifact_id_raw and not provenance_json_raw:
            lean_semantic_compatibility_id = SemanticCompatibilityId(sem_compat_id_raw)
            artifact_identity = None
        else:
            artifact_identity = decode_signal_artifact_identity(
                artifact_id_raw=artifact_id_raw,
                semantic_compatibility_id_raw=sem_compat_id_raw,
                provenance_json_raw=provenance_json_raw,
            )
        return CandidateObservation(
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
            payload=payload,
            workflow=row["workflow"],
            window_sessions=row["window_sessions"],
            data_as_of_date=(
                date.fromisoformat(data_as_of_date_raw) if data_as_of_date_raw else None
            ),
            config_hash=row["config_hash"],
            decision_at=(
                datetime.fromisoformat(row["decision_at"]) if row["decision_at"] else None
            ),
            latest_completed_session=(
                date.fromisoformat(row["latest_completed_session"])
                if row["latest_completed_session"]
                else None
            ),
            analysis_as_of=(
                date.fromisoformat(row["analysis_as_of"]) if row["analysis_as_of"] else None
            ),
            market_session_name=row["market_session_name"] or None,
            is_eod_pending=_bool_from_db(row["is_eod_pending"]),
            resolution_source=row["resolution_source"] or None,
            resolution_notes=_resolution_notes_from_db(row["resolution_notes_json"]),
            artifact_identity=artifact_identity,
            observation_contract=row["observation_contract"] or None,
            semantic_compatibility_id=lean_semantic_compatibility_id,
        )


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
