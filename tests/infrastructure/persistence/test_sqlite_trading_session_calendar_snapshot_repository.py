"""Authority uniqueness and concurrent-write recovery for calendar snapshots."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotRepository,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return tuple(out)


def _snap(
    *,
    sessions: tuple[date, ...],
    revision: str = "rev-1",
    coverage_start: date = date(2026, 7, 1),
    coverage_end: date = date(2026, 7, 31),
    captured_at: datetime = NOW,
) -> TradingSessionCalendarSnapshot:
    return TradingSessionCalendarSnapshot.create(
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        ordered_sessions=sessions,
        source_revision=revision,
        captured_at=captured_at,
    )


def test_unique_authority_index_exists(tmp_path: Path) -> None:
    db = tmp_path / "idx.db"
    SQLiteTradingSessionCalendarSnapshotRepository(db)
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='uq_trading_session_calendar_authority'"
        ).fetchall()
    assert rows


def test_divergent_sessions_same_authority_key_raise(tmp_path: Path) -> None:
    db = tmp_path / "div.db"
    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions_a = _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    sessions_b = sessions_a[:-1] + (date(2026, 7, 21),)
    a = _snap(sessions=sessions_a)
    b = _snap(
        sessions=sessions_b,
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert store.add_snapshot(a) is True
    with pytest.raises(LearningContractError, match="source conflict"):
        store.add_snapshot(b)
    assert len(store.list_snapshots()) == 1


def test_idempotent_reinsert_same_content(tmp_path: Path) -> None:
    db = tmp_path / "idem.db"
    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions = _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    a = _snap(sessions=sessions)
    assert store.add_snapshot(a) is True
    # Same natural key + sessions, different operational captured_at → same snapshot_id.
    b = _snap(
        sessions=sessions,
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert a.snapshot_id == b.snapshot_id
    assert store.add_snapshot(b) is False
    assert len(store.list_snapshots()) == 1


def test_migration_fails_on_preexisting_authority_conflict(tmp_path: Path) -> None:
    db = tmp_path / "migrate.db"
    sessions_a = _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    sessions_b = sessions_a[:-1] + (date(2026, 7, 21),)
    a = _snap(sessions=sessions_a)
    b = _snap(
        sessions=sessions_b,
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    # Create table without unique index and seed dual natural-key rows.
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE trading_session_calendar_snapshots (
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
        )
        for snap in (a, b):
            payload = snap.to_dict()
            import json

            conn.execute(
                """
                INSERT INTO trading_session_calendar_snapshots (
                    snapshot_id, contract_id, source, benchmark,
                    coverage_start, coverage_end, ordered_sessions_json,
                    source_revision, captured_at, payload_digest, artifact_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id,
                    snap.contract_id,
                    snap.source,
                    snap.benchmark,
                    snap.coverage_start.isoformat(),
                    snap.coverage_end.isoformat(),
                    json.dumps([s.isoformat() for s in snap.ordered_sessions]),
                    snap.source_revision,
                    snap.captured_at.isoformat(),
                    snap.payload_digest,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
        conn.commit()

    with pytest.raises(LearningContractError, match="migration integrity"):
        SQLiteTradingSessionCalendarSnapshotRepository(db)


def test_concurrent_agreeing_writers_are_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "race-ok.db"
    # Ensure schema once before threads contend on inserts.
    SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions = _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    snap = _snap(sessions=sessions)
    barrier = threading.Barrier(8)
    results: list[bool | BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            store = SQLiteTradingSessionCalendarSnapshotRepository(db)
            barrier.wait(timeout=5)
            inserted = store.add_snapshot(snap)
            with lock:
                results.append(inserted)
        except BaseException as exc:  # noqa: BLE001 — surface in assertions
            with lock:
                results.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(worker) for _ in range(8)]
        for fut in futs:
            fut.result(timeout=10)

    assert all(not isinstance(r, BaseException) for r in results), results
    assert sum(1 for r in results if r is True) == 1
    assert sum(1 for r in results if r is False) == 7
    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    assert len(store.list_snapshots()) == 1


def test_concurrent_divergent_writers_raise_source_conflict(tmp_path: Path) -> None:
    db = tmp_path / "race-conflict.db"
    SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions_a = _weekdays(date(2026, 7, 1), date(2026, 7, 20))
    sessions_b = sessions_a[:-1] + (date(2026, 7, 21),)
    a = _snap(sessions=sessions_a)
    b = _snap(
        sessions=sessions_b,
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert a.snapshot_id != b.snapshot_id
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(snap: TradingSessionCalendarSnapshot) -> None:
        store = SQLiteTradingSessionCalendarSnapshotRepository(db)
        barrier.wait(timeout=5)
        try:
            inserted = store.add_snapshot(snap)
            with lock:
                outcomes.append(f"ok:{inserted}")
        except LearningContractError as exc:
            with lock:
                outcomes.append(f"conflict:{exc}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(worker, a)
        fb = pool.submit(worker, b)
        fa.result(timeout=10)
        fb.result(timeout=10)

    assert len(outcomes) == 2
    # One insert succeeds; the other must surface a typed source conflict.
    # Depending on timing, both may race through peer-check and one hits unique index.
    oks = [o for o in outcomes if o.startswith("ok:")]
    conflicts = [o for o in outcomes if o.startswith("conflict:")]
    assert len(oks) == 1
    assert len(conflicts) == 1
    assert "source conflict" in conflicts[0]
    store = SQLiteTradingSessionCalendarSnapshotRepository(db)
    assert len(store.list_snapshots()) == 1
