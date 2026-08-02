"""SQLite persistence for immutable trading-session calendar snapshots.

Write path may ensure schema. Read-only status path uses mode=ro and never
creates files, tables, or directories. Normalized columns are reconciled against
artifact_json on every read.

Natural authority uniqueness is enforced by a UNIQUE INDEX on
(contract_id, source, benchmark, coverage_start, coverage_end, source_revision).
Concurrent writers that race past the pre-INSERT peer check still collide on
the index; IntegrityError recovery reloads and is either idempotent or a
typed source conflict.

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

_AUTHORITY_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_trading_session_calendar_authority
ON trading_session_calendar_snapshots (
    contract_id,
    source,
    benchmark,
    coverage_start,
    coverage_end,
    source_revision
)
"""

_SELECT_COLUMNS = (
    "snapshot_id, contract_id, source, benchmark, coverage_start, coverage_end, "
    "ordered_sessions_json, source_revision, captured_at, payload_digest, artifact_json"
)


class SQLiteTradingSessionCalendarSnapshotRepository:
    """Write-capable snapshot store (ensures table + authority uniqueness on construct)."""

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
            _assert_no_existing_authority_conflicts(conn)
            conn.execute(_AUTHORITY_UNIQUE_INDEX_SQL)
            conn.commit()

    def add_snapshot(self, snapshot: TradingSessionCalendarSnapshot) -> bool:
        validate_active_stockbit_calendar_snapshot(snapshot)
        payload = snapshot.to_dict()
        sessions_json = json.dumps([s.isoformat() for s in snapshot.ordered_sessions])
        artifact_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            # Natural authority key: contract/source/benchmark/coverage/revision.
            # Same key with different sessions is a source conflict — never insert.
            peers = _fetch_peers_by_authority(conn, snapshot)
            for peer in peers:
                loaded = _row_to_snapshot(peer, requested_id=peer["snapshot_id"])
                if loaded.ordered_sessions != snapshot.ordered_sessions:
                    raise _source_conflict_error(existing=loaded, incoming=snapshot)
                if loaded.snapshot_id == snapshot.snapshot_id:
                    # Exact idempotent hit (same identity).
                    return False

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
            try:
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
            except sqlite3.IntegrityError:
                # Concurrent writer won the race on PK or natural authority key.
                conn.rollback()
                return _resolve_integrity_race(conn, snapshot)
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


def _assert_no_existing_authority_conflicts(conn: sqlite3.Connection) -> None:
    """Fail closed before CREATE UNIQUE INDEX when pre-migration dual rows exist."""
    rows = conn.execute(
        """
        SELECT contract_id, source, benchmark, coverage_start, coverage_end,
               source_revision, COUNT(*) AS n
        FROM trading_session_calendar_snapshots
        GROUP BY contract_id, source, benchmark, coverage_start, coverage_end,
                 source_revision
        HAVING n > 1
        """
    ).fetchall()
    if not rows:
        return
    sample = rows[0]
    raise LearningContractError(
        "calendar snapshot migration integrity error: natural authority key has "
        f"{sample['n']} rows for "
        f"contract_id={sample['contract_id']!r} source={sample['source']!r} "
        f"benchmark={sample['benchmark']!r} "
        f"coverage={sample['coverage_start']}..{sample['coverage_end']} "
        f"source_revision={sample['source_revision']!r}. "
        "Resolve divergent sessions before opening the write repository."
    )


def _fetch_peers_by_authority(
    conn: sqlite3.Connection,
    snapshot: TradingSessionCalendarSnapshot,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots "
            "WHERE contract_id = ? AND source = ? AND benchmark = ? "
            "AND coverage_start = ? AND coverage_end = ? AND source_revision = ?",
            (
                snapshot.contract_id,
                snapshot.source,
                snapshot.benchmark,
                snapshot.coverage_start.isoformat(),
                snapshot.coverage_end.isoformat(),
                snapshot.source_revision,
            ),
        ).fetchall()
    )


def _resolve_integrity_race(
    conn: sqlite3.Connection,
    snapshot: TradingSessionCalendarSnapshot,
) -> bool:
    """After IntegrityError: reload by natural key (or PK) and reconcile.

    Returns False when the winning row is identity-compatible (idempotent).
    Raises LearningContractError when sessions/identity diverge.
    """
    peers = _fetch_peers_by_authority(conn, snapshot)
    if peers:
        for peer in peers:
            loaded = _row_to_snapshot(peer, requested_id=peer["snapshot_id"])
            if loaded.ordered_sessions != snapshot.ordered_sessions:
                raise _source_conflict_error(existing=loaded, incoming=snapshot)
            # Sessions agree on the natural key — idempotent regardless of snapshot_id.
            return False

    # PK collision without matching natural-key peer (should be rare).
    existing = conn.execute(
        f"SELECT {_SELECT_COLUMNS} FROM trading_session_calendar_snapshots WHERE snapshot_id = ?",
        (snapshot.snapshot_id,),
    ).fetchone()
    if existing is None:
        raise LearningContractError(
            "calendar snapshot insert failed with IntegrityError but no peer row "
            f"was found for snapshot_id={snapshot.snapshot_id!r}"
        )
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


def _source_conflict_error(
    *,
    existing: TradingSessionCalendarSnapshot,
    incoming: TradingSessionCalendarSnapshot,
) -> LearningContractError:
    return LearningContractError(
        "calendar source conflict: identical contract/source/benchmark/"
        "coverage/source_revision with divergent sessions "
        f"(existing={existing.snapshot_id!r}, "
        f"incoming={incoming.snapshot_id!r}, "
        f"revision={incoming.source_revision!r}, "
        f"coverage={incoming.coverage_start.isoformat()}.."
        f"{incoming.coverage_end.isoformat()})"
    )


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
    expected_artifact = json.dumps(snap.to_dict(), sort_keys=True, separators=(",", ":"))
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
        ("artifact_json", row["artifact_json"], expected_artifact),
    )
    for name, left, right in checks:
        if left != right:
            raise TradingSessionCalendarSnapshotReadError(
                f"row/artifact mismatch on {name}: column={left!r} artifact={right!r}"
            )
