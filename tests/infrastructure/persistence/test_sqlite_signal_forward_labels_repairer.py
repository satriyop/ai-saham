"""Tests for SQLiteSignalForwardLabelsRepairer (DQ-001L)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_signal_forward_labels_repairer import (
    SQLiteSignalForwardLabelsRepairer,
)

_REPAIR_RUN_ID = "test-run-001"


def _build_schemas(db_path: Path) -> None:
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteSignalForwardLabelsRepository(db_path)
    SQLiteCandidateObservationsRepository(db_path)


def _insert_co_row(
    db_path: Path,
    *,
    ticker: str,
    snapshot_date: str = "2026-07-01",
    captured_at: str = "2026-07-01T00:00:00",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, snapshot_date, captured_at, 1, "{}", "hash1"),
    )
    conn.commit()
    conn.close()


def _insert_label_row(
    db_path: Path,
    *,
    ticker: str,
    signal_date: str = "2026-07-01",
    observation_captured_at: str = "2026-07-01T00:00:00",
    horizon: str = "SHORT",
    outcome_label: str = "UP",
) -> int:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ticker,
            signal_date,
            horizon,
            observation_captured_at,
            outcome_label,
            '{"v":1}',
            1,
            "2026-07-16T00:00:00",
            "2026-07-16T00:00:00",
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def _make_repairer(db_path: Path) -> SQLiteSignalForwardLabelsRepairer:
    return SQLiteSignalForwardLabelsRepairer(db_path)


# ── quarantine table creation ────────────────────────────────────────────────


def test_ensure_quarantine_table_creates_table(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "signal_forward_labels_quarantine" in tables


def test_ensure_quarantine_table_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "signal_forward_labels_quarantine" in tables


# ── apply: quarantine + delete ───────────────────────────────────────────────


def test_apply_moves_only_orphan_labels_into_quarantine(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")  # canonical
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM signal_forward_labels_quarantine"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "BBCA"
    assert rows[0]["signal_date"] == "2026-07-02"
    assert rows[0]["repair_run_id"] == _REPAIR_RUN_ID
    assert rows[0]["original_table"] == "signal_forward_labels"


def test_apply_preserves_non_orphan_labels(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")  # canonical
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT signal_date FROM signal_forward_labels ORDER BY signal_date"
        ).fetchall()
    assert [r[0] for r in remaining] == ["2026-07-01"]


def test_apply_deletes_orphan_labels_from_canonical_table(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    orphan_id = _insert_label_row(
        db_path, ticker="BBCA", signal_date="2026-07-02"
    )

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels WHERE id = ?",
            (orphan_id,),
        ).fetchone()[0]
    assert remaining == 0


def test_apply_returns_matching_quarantined_and_deleted_counts(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan
    _insert_label_row(db_path, ticker="BBRI", signal_date="2026-07-03")  # orphan

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    assert quarantined == 2
    assert deleted == 2


# ── idempotency ──────────────────────────────────────────────────────────────


def test_second_apply_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")  # canonical
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    first_q, first_d = repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)
    assert first_q == 1
    assert first_d == 1

    second_q, second_d = repairer.quarantine_and_delete_orphans("second-run")
    assert second_q == 0
    assert second_d == 0

    with sqlite3.connect(str(db_path)) as conn:
        qc = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels_quarantine"
        ).fetchone()[0]
    assert qc == 1


# ── ensure alone does not mutate source ──────────────────────────────────────


def test_ensure_quarantine_table_alone_does_not_mutate_source_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan

    with sqlite3.connect(str(db_path)) as conn:
        count_before = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels"
        ).fetchone()[0]

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        count_after = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels"
        ).fetchone()[0]

    assert count_before == count_after == 1


# ── rollback on failure ──────────────────────────────────────────────────────


def test_rollback_preserves_source_and_quarantine_on_simulated_failure(
    tmp_path: Path,
):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")

    class _FailingRepairer(SQLiteSignalForwardLabelsRepairer):
        def quarantine_and_delete_orphans(
            self, repair_run_id: str
        ) -> tuple[int, int]:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                conn.execute(
                    "INSERT INTO signal_forward_labels_quarantine "
                    "(source_row_id, ticker, quarantine_reason, quarantined_at, "
                    "repair_run_id, original_table, quarantine_schema_version) "
                    "VALUES (999, 'FAIL', 'TEST', '2026-07-16T00:00:00+00:00', ?, "
                    "'signal_forward_labels', 1)",
                    (repair_run_id,),
                )
                raise RuntimeError("Simulated failure mid-quarantine")
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    repairer = _FailingRepairer(db_path)
    repairer.ensure_quarantine_table()

    with pytest.raises(RuntimeError, match="Simulated failure"):
        repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT signal_date FROM signal_forward_labels"
        ).fetchall()
    assert len(remaining) == 1

    with sqlite3.connect(str(db_path)) as conn:
        qc = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels_quarantine"
        ).fetchone()[0]
    assert qc == 0


def test_delete_count_mismatch_raises_and_rolls_back(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")

    class _MismatchRepairer(SQLiteSignalForwardLabelsRepairer):
        def quarantine_and_delete_orphans(
            self, repair_run_id: str
        ) -> tuple[int, int]:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                row = conn.execute(
                    "SELECT l.rowid AS _source_rowid "
                    "FROM signal_forward_labels l "
                    "LEFT JOIN candidate_observations o "
                    "ON o.ticker = l.ticker "
                    "AND o.snapshot_date = l.signal_date "
                    "AND o.captured_at = l.observation_captured_at "
                    "WHERE o.ticker IS NULL"
                ).fetchone()
                source_rowid = row["_source_rowid"]
                conn.execute(
                    "INSERT INTO signal_forward_labels_quarantine "
                    "(source_row_id, ticker, quarantine_reason, quarantined_at, "
                    "repair_run_id, original_table, quarantine_schema_version) "
                    "VALUES (?, 'FAIL', 'TEST', '2026-07-16T00:00:00+00:00', ?, "
                    "'signal_forward_labels', 1)",
                    (source_rowid, repair_run_id),
                )
                delete_cursor = conn.execute(
                    "DELETE FROM signal_forward_labels WHERE rowid = ?",
                    (source_rowid + 9999,),
                )
                if delete_cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to delete 1 row for source "
                        f"rowid={source_rowid} "
                        f"but deleted {delete_cursor.rowcount}. Rolling back."
                    )
                conn.commit()
                return 1, 1
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    repairer = _MismatchRepairer(db_path)
    repairer.ensure_quarantine_table()

    with pytest.raises(RuntimeError, match="Expected to delete 1 row"):
        repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT signal_date FROM signal_forward_labels"
        ).fetchall()
    assert len(remaining) == 1

    with sqlite3.connect(str(db_path)) as conn:
        qc = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels_quarantine"
        ).fetchone()[0]
    assert qc == 0


# ── full column preservation ─────────────────────────────────────────────────


def test_quarantine_preserves_full_label_fields(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(
        db_path,
        ticker="BBCA",
        signal_date="2026-07-02",
        horizon="LONG",
        outcome_label="DOWN",
    )

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM signal_forward_labels_quarantine WHERE ticker = 'BBCA'"
        ).fetchone()
    assert row["ticker"] == "BBCA"
    assert row["signal_date"] == "2026-07-02"
    assert row["horizon"] == "LONG"
    assert row["outcome_label"] == "DOWN"
    assert row["quarantine_reason"] == "ORPHAN_CANDIDATE_OBSERVATION"
    assert row["source_row_id"] is not None
    assert row["repair_run_id"] == _REPAIR_RUN_ID


# ── works without optional id column ─────────────────────────────────────────


def test_apply_works_when_source_table_has_no_id_column(tmp_path: Path):
    """Regression: rowid is the stable repair identity, not the optional id."""
    db_path = tmp_path / "no_id.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candidate_observations ("
        "ticker TEXT NOT NULL, snapshot_date TEXT NOT NULL, "
        "captured_at TEXT NOT NULL, schema_version INTEGER NOT NULL, "
        "payload_json TEXT NOT NULL, config_hash TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash) "
        "VALUES ('BBCA', '2026-07-01', '2026-07-01T00:00:00', 1, '{}', 'hash1')"
    )
    conn.execute(
        "CREATE TABLE signal_forward_labels ("
        "ticker TEXT NOT NULL, signal_date TEXT NOT NULL, "
        "horizon TEXT NOT NULL, observation_captured_at TEXT NOT NULL DEFAULT '', "
        "outcome_label TEXT NOT NULL, fingerprint_json TEXT NOT NULL, "
        "schema_version INTEGER NOT NULL DEFAULT 1, "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "INSERT INTO signal_forward_labels "
        "(ticker, signal_date, horizon, observation_captured_at, "
        "outcome_label, fingerprint_json, schema_version, created_at, updated_at) "
        "VALUES ('BBCA', '2026-07-02', 'SHORT', '2026-07-02T00:00:00', "
        "'UP', '{\"v\":1}', 1, '2026-07-16T00:00:00', '2026-07-16T00:00:00')"
    )
    conn.commit()
    conn.close()

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_orphans(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM signal_forward_labels"
        ).fetchone()[0]
    assert remaining == 0

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM signal_forward_labels_quarantine WHERE ticker = 'BBCA'"
        ).fetchone()
    assert row["source_row_id"] is not None
