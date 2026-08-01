"""SQLite persistence for immutable trading-session calendar snapshots.

Write path may ensure schema. Read-only status path uses mode=ro and never
creates files, tables, or directories.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Sequence

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
    validate_trading_session_calendar_snapshot,
)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trading_session_calendar_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    source TEXT NOT NULL,
    benchmark TEXT NOT NULL,
    coverage_start TEXT NOT NULL,
    coverage_end TEXT NOT NULL,
    ordered_sessions_json TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    artifact_json TEXT NOT NULL
)
"""


class SQLiteTradingSessionCalendarSnapshotRepository:
    """Write-capable snapshot store (ensures table on construct)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_TABLE_SQL)
            conn.commit()

    def add_snapshot(self, snapshot: TradingSessionCalendarSnapshot) -> None:
        validate_trading_session_calendar_snapshot(snapshot)
        payload = snapshot.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO trading_session_calendar_snapshots (
                    snapshot_id, contract_id, source, benchmark,
                    coverage_start, coverage_end, ordered_sessions_json,
                    source_revision, captured_at, payload_digest, artifact_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.contract_id,
                    snapshot.source,
                    snapshot.benchmark,
                    snapshot.coverage_start.isoformat(),
                    snapshot.coverage_end.isoformat(),
                    json.dumps([s.isoformat() for s in snapshot.ordered_sessions]),
                    snapshot.source_revision,
                    snapshot.captured_at.isoformat(),
                    snapshot.payload_digest,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            conn.commit()

    def get_snapshot(self, snapshot_id: str) -> TradingSessionCalendarSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_json FROM trading_session_calendar_snapshots "
                "WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_snapshot(row)

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT artifact_json FROM trading_session_calendar_snapshots "
                "ORDER BY coverage_start ASC, coverage_end ASC"
            ).fetchall()
        return tuple(_row_to_snapshot(row) for row in rows)

    def find_covering_snapshot(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot | None:
        for snap in self.list_snapshots():
            if snap.coverage_start <= coverage_start and snap.coverage_end >= coverage_end:
                return snap
        return None


class SQLiteTradingSessionCalendarSnapshotReadRepository:
    """Read-only snapshot access for status / readiness (mode=ro, no DDL)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"database does not exist (status is read-only): {self._db_path}"
            )
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_snapshot(self, snapshot_id: str) -> TradingSessionCalendarSnapshot | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT artifact_json FROM trading_session_calendar_snapshots "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
        except FileNotFoundError:
            return None
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return _row_to_snapshot(row)

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT artifact_json FROM trading_session_calendar_snapshots "
                    "ORDER BY coverage_start ASC, coverage_end ASC"
                ).fetchall()
        except FileNotFoundError:
            return ()
        except sqlite3.Error:
            return ()
        return tuple(_row_to_snapshot(row) for row in rows)

    def find_covering_snapshot(
        self,
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> TradingSessionCalendarSnapshot | None:
        for snap in self.list_snapshots():
            if snap.coverage_start <= coverage_start and snap.coverage_end >= coverage_end:
                return snap
        return None


def _row_to_snapshot(row: sqlite3.Row) -> TradingSessionCalendarSnapshot:
    try:
        raw = json.loads(row["artifact_json"])
        snap = TradingSessionCalendarSnapshot.from_mapping(raw)
        validate_trading_session_calendar_snapshot(snap)
        return snap
    except (TypeError, ValueError, KeyError, LearningContractError, json.JSONDecodeError) as exc:
        raise LearningContractError(f"stored calendar snapshot corrupt: {exc}") from exc
