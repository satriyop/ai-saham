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
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_many(self, observations: list[CandidateObservation]) -> None:
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
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO candidate_observations
                    (ticker, snapshot_date, captured_at, schema_version, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_latest(self, ticker: str, snapshot_date: date) -> CandidateObservation | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ticker, snapshot_date, captured_at, schema_version, payload_json
                FROM candidate_observations
                WHERE ticker = ? AND snapshot_date = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (ticker.upper(), snapshot_date.isoformat()),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        schema_version = int(payload.get("schema_version", row["schema_version"]))
        if schema_version > 1:
            raise ValueError(f"Unsupported candidate observation schema_version={schema_version}")
        payload.setdefault("schema_version", schema_version)
        return CandidateObservation(
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
            payload=payload,
        )

    def get_at(
        self,
        ticker: str,
        snapshot_date: date,
        captured_at: datetime,
    ) -> CandidateObservation | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ticker, snapshot_date, captured_at, schema_version, payload_json
                FROM candidate_observations
                WHERE ticker = ? AND snapshot_date = ? AND captured_at = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ticker.upper(), snapshot_date.isoformat(), captured_at.isoformat()),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        schema_version = int(payload.get("schema_version", row["schema_version"]))
        if schema_version > 1:
            raise ValueError(f"Unsupported candidate observation schema_version={schema_version}")
        payload.setdefault("schema_version", schema_version)
        return CandidateObservation(
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
            payload=payload,
        )

    def list_recent(
        self,
        ticker: str,
        *,
        before_date: date | None = None,
        limit: int = 20,
    ) -> list[CandidateObservation]:
        query = """
            SELECT ticker, snapshot_date, captured_at, schema_version, payload_json
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

    def _row_to_observation(self, row: sqlite3.Row) -> CandidateObservation:
        payload = json.loads(row["payload_json"])
        schema_version = int(payload.get("schema_version", row["schema_version"]))
        if schema_version > 1:
            raise ValueError(f"Unsupported candidate observation schema_version={schema_version}")
        payload.setdefault("schema_version", schema_version)
        return CandidateObservation(
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            captured_at=datetime.fromisoformat(row["captured_at"]),
            payload=payload,
        )
