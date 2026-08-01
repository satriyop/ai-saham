"""SQLite persistence for immutable trading-session calendar snapshots.

Write path may ensure schema. Read-only status path uses mode=ro and never
creates files, tables, or directories. Normalized columns are reconciled against
artifact_json on every read.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotReadError,
)
from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
    validate_active_stockbit_calendar_snapshot,
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

_SELECT_COLUMNS = (
    "snapshot_id, contract_id, source, benchmark, coverage_start, coverage_end, "
    "ordered_sessions_json, source_revision, captured_at, payload_digest, artifact_json"
)


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

    def add_snapshot(self, snapshot: TradingSessionCalendarSnapshot) -> bool:
        validate_active_stockbit_calendar_snapshot(snapshot)
        payload = snapshot.to_dict()
        sessions_json = json.dumps([s.isoformat() for s in snapshot.ordered_sessions])
        artifact_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            existing = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
                "WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if existing is not None:
                loaded = _row_to_snapshot(existing, requested_id=snapshot.snapshot_id)
                if (
                    loaded.payload_digest != snapshot.payload_digest
                    or loaded.ordered_sessions != snapshot.ordered_sessions
                    or loaded.source_revision != snapshot.source_revision
                    or loaded.coverage_start != snapshot.coverage_start
                    or loaded.coverage_end != snapshot.coverage_end
                ):
                    raise LearningContractError(
                        "calendar snapshot conflict: existing row incompatible with "
                        f"incoming snapshot_id={snapshot.snapshot_id!r}"
                    )
                return False
            conn.execute(
                """
                INSERT INTO trading_session_calendar_snapshots (
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
                    sessions_json,
                    snapshot.source_revision,
                    snapshot.captured_at.isoformat(),
                    snapshot.payload_digest,
                    artifact_json,
                ),
            )
            conn.commit()
        return True

    def get_snapshot(self, snapshot_id: str) -> TradingSessionCalendarSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
                "WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_snapshot(row, requested_id=snapshot_id)

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
                "ORDER BY coverage_start ASC, coverage_end ASC, captured_at ASC, snapshot_id ASC"
            ).fetchall()
        return tuple(_row_to_snapshot(row, requested_id=row["snapshot_id"]) for row in rows)


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
                    f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
        except FileNotFoundError:
            return None
        except sqlite3.Error as exc:
            raise TradingSessionCalendarSnapshotReadError(
                f"sqlite error loading calendar snapshot {snapshot_id!r}: {exc}"
            ) from exc
        if row is None:
            return None
        return _row_to_snapshot(row, requested_id=snapshot_id)

    def list_snapshots(self) -> Sequence[TradingSessionCalendarSnapshot]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
                    "ORDER BY coverage_start ASC, coverage_end ASC, "
                    "captured_at ASC, snapshot_id ASC"
                ).fetchall()
        except FileNotFoundError:
            return ()
        except sqlite3.Error as exc:
            raise TradingSessionCalendarSnapshotReadError(
                f"sqlite error listing calendar snapshots: {exc}"
            ) from exc
        return tuple(_row_to_snapshot(row, requested_id=row["snapshot_id"]) for row in rows)


def _row_to_snapshot(
    row: sqlite3.Row,
    *,
    requested_id: str,
) -> TradingSessionCalendarSnapshot:
    try:
        raw = json.loads(row["artifact_json"])
        snap = TradingSessionCalendarSnapshot.from_mapping(raw)
        validate_trading_session_calendar_snapshot(snap)
        validate_active_stockbit_calendar_snapshot(snap)
        _reconcile_row_columns(row, snap)
        if snap.snapshot_id != requested_id:
            raise TradingSessionCalendarSnapshotReadError(
                f"loaded snapshot_id {snap.snapshot_id!r} != requested {requested_id!r}"
            )
        return snap
    except TradingSessionCalendarSnapshotReadError:
        raise
    except (
        TypeError,
        ValueError,
        KeyError,
        LearningContractError,
        json.JSONDecodeError,
    ) as exc:
        raise TradingSessionCalendarSnapshotReadError(
            f"stored calendar snapshot corrupt: {exc}"
        ) from exc


def _reconcile_row_columns(
    row: sqlite3.Row,
    snap: TradingSessionCalendarSnapshot,
) -> None:
    sessions_json = json.dumps([s.isoformat() for s in snap.ordered_sessions])
    checks = (
        ("snapshot_id", row["snapshot_id"], snap.snapshot_id),
        ("contract_id", row["contract_id"], snap.contract_id),
        ("source", row["source"], snap.source),
        ("benchmark", row["benchmark"], snap.benchmark),
        ("coverage_start", row["coverage_start"], snap.coverage_start.isoformat()),
        ("coverage_end", row["coverage_end"], snap.coverage_end.isoformat()),
        ("ordered_sessions_json", row["ordered_sessions_json"], sessions_json),
        ("source_revision", row["source_revision"], snap.source_revision),
        ("captured_at", row["captured_at"], snap.captured_at.isoformat()),
        ("payload_digest", row["payload_digest"], snap.payload_digest),
    )
    for name, left, right in checks:
        if str(left) != str(right):
            raise TradingSessionCalendarSnapshotReadError(
                f"row/artifact mismatch on {name}: column={left!r} artifact={right!r}"
            )
