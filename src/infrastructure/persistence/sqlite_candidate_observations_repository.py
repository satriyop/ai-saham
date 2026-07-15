"""SQLite repository for replayable candidate observations."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

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

_SELECT_COLUMNS = (
    "ticker, snapshot_date, captured_at, schema_version, payload_json, "
    "workflow, window_sessions, data_as_of_date, config_hash"
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
                )
            )
        with self._connect() as conn:
            conn.executemany(
                f"""
                INSERT INTO candidate_observations
                    (ticker, snapshot_date, captured_at, schema_version, payload_json,
                     workflow, window_sessions, data_as_of_date, config_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT {_IDENTITY_CONFLICT_TARGET} WHERE config_hash != ''
                DO UPDATE SET
                    captured_at = excluded.captured_at,
                    schema_version = excluded.schema_version,
                    payload_json = excluded.payload_json
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

        Canonical = config_hash != ''. A ticker with observations across
        several window_sessions returns one row per window, not just the
        latest.
        """
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM candidate_observations
                WHERE snapshot_date = ? AND config_hash != ''
                ORDER BY ticker ASC, window_sessions ASC, data_as_of_date DESC,
                         captured_at DESC, id DESC
                """,
                (snapshot_date.isoformat(),),
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

    def _row_to_observation(self, row: sqlite3.Row) -> CandidateObservation:
        payload = json.loads(row["payload_json"])
        schema_version = int(payload.get("schema_version", row["schema_version"]))
        if schema_version > 1:
            raise ValueError(f"Unsupported candidate observation schema_version={schema_version}")
        payload.setdefault("schema_version", schema_version)
        data_as_of_date_raw = row["data_as_of_date"]
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
        )
