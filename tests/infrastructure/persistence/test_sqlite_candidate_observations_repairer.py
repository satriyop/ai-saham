"""Tests for SQLiteCandidateObservationsRepairer (DQ-001J)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_candidate_observations_repairer import (
    SQLiteCandidateObservationsRepairer,
)

_REPAIR_RUN_ID = "test-run-001"


def _build_schema(db_path: Path) -> None:
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteCandidateObservationsRepository(db_path)


def _insert_row(
    db_path: Path,
    *,
    ticker: str,
    snapshot_date: str = "2026-07-01",
    config_hash: str = "",
) -> int:
    schema_version = 2 if config_hash != "" else 1
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json, config_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ticker, snapshot_date, f"{snapshot_date}T00:00:00", schema_version, "{}", config_hash),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def _make_repairer(db_path: Path) -> SQLiteCandidateObservationsRepairer:
    return SQLiteCandidateObservationsRepairer(db_path)


# ── quarantine table creation ────────────────────────────────────────────────


def test_ensure_quarantine_table_creates_table(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "candidate_observations_quarantine" in tables


def test_ensure_quarantine_table_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "candidate_observations_quarantine" in tables


# ── apply: quarantine + delete ───────────────────────────────────────────────


def test_apply_moves_only_legacy_rows_into_quarantine(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")
    _insert_row(db_path, ticker="CANON1", config_hash="hash1")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM candidate_observations_quarantine").fetchall()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "LEGACY1"
    assert rows[0]["repair_run_id"] == _REPAIR_RUN_ID
    assert rows[0]["original_table"] == "candidate_observations"


def test_apply_preserves_canonical_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")
    _insert_row(db_path, ticker="CANON1", config_hash="hash1")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT ticker FROM candidate_observations"
        ).fetchall()
    assert [r[0] for r in remaining] == ["CANON1"]


def test_apply_deletes_legacy_rows_from_canonical_table(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    row_id = _insert_row(db_path, ticker="LEGACY1", config_hash="")
    _insert_row(db_path, ticker="CANON1", config_hash="hash1")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM candidate_observations WHERE id = ?", (row_id,)
        ).fetchone()[0]
    assert remaining == 0


def test_apply_returns_matching_quarantined_and_deleted_counts(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")
    _insert_row(db_path, ticker="LEGACY2", config_hash="   ")
    _insert_row(db_path, ticker="CANON1", config_hash="hash1")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 2
    assert deleted == 2


# ── idempotency ──────────────────────────────────────────────────────────────


def test_second_apply_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")
    _insert_row(db_path, ticker="CANON1", config_hash="hash1")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    first_quarantined, first_deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)
    assert first_quarantined == 1
    assert first_deleted == 1

    second_quarantined, second_deleted = repairer.quarantine_and_delete_legacy("second-run")
    assert second_quarantined == 0
    assert second_deleted == 0

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM candidate_observations_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 1


# ── dry-run / no mutation ────────────────────────────────────────────────────


def test_ensure_quarantine_table_alone_does_not_mutate_source_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")

    with sqlite3.connect(str(db_path)) as conn:
        count_before = conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0]

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()

    with sqlite3.connect(str(db_path)) as conn:
        count_after = conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0]

    assert count_before == count_after == 1


# ── rollback on failure ──────────────────────────────────────────────────────


def test_rollback_preserves_source_and_quarantine_rows_on_simulated_failure(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")

    class _FailingRepairer(SQLiteCandidateObservationsRepairer):
        def quarantine_and_delete_legacy(self, repair_run_id: str) -> tuple[int, int]:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                conn.execute(
                    "INSERT INTO candidate_observations_quarantine "
                    "(source_row_id, id, ticker, quarantine_reason, quarantined_at, "
                    "repair_run_id, original_table, quarantine_schema_version) "
                    "VALUES (999, 999, 'LEGACY1', 'TEST', '2026-07-16T00:00:00+00:00', ?, "
                    "'candidate_observations', 1)",
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
        repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM candidate_observations").fetchall()
    assert [r[0] for r in remaining] == ["LEGACY1"]

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM candidate_observations_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 0


def test_delete_count_mismatch_raises_and_rolls_back(tmp_path: Path):
    """Force the delete step to target a nonexistent id (0 rows affected) to
    exercise the RuntimeError guard and confirm the transaction rolls back:
    neither the quarantine insert nor the source delete survive."""
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="LEGACY1", config_hash="")

    class _MismatchRepairer(SQLiteCandidateObservationsRepairer):
        def quarantine_and_delete_legacy(self, repair_run_id: str) -> tuple[int, int]:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                row = conn.execute(
                    "SELECT rowid AS _source_rowid, id, ticker FROM candidate_observations "
                    "WHERE config_hash IS NULL OR TRIM(config_hash) = ''"
                ).fetchone()
                source_rowid = row["_source_rowid"]
                conn.execute(
                    "INSERT INTO candidate_observations_quarantine "
                    "(source_row_id, id, ticker, quarantine_reason, quarantined_at, "
                    "repair_run_id, original_table, quarantine_schema_version) "
                    "VALUES (?, ?, ?, 'TEST', '2026-07-16T00:00:00+00:00', ?, "
                    "'candidate_observations', 1)",
                    (source_rowid, row["id"], row["ticker"], repair_run_id),
                )
                delete_cursor = conn.execute(
                    "DELETE FROM candidate_observations WHERE rowid = ?",
                    (source_rowid + 9999,),
                )
                if delete_cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to delete 1 row for source rowid={source_rowid} "
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
        repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT ticker FROM candidate_observations").fetchall()
    assert [r[0] for r in remaining] == ["LEGACY1"]

    with sqlite3.connect(str(db_path)) as conn:
        quarantine_count = conn.execute(
            "SELECT COUNT(*) FROM candidate_observations_quarantine"
        ).fetchone()[0]
    assert quarantine_count == 0


# ── missing optional columns ─────────────────────────────────────────────────


def test_missing_optional_columns_are_stored_as_null_in_quarantine(tmp_path: Path):
    db_path = tmp_path / "legacy_schema.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE candidate_observations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker         TEXT NOT NULL,
            snapshot_date  TEXT NOT NULL,
            captured_at    TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json   TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json) "
        "VALUES ('BBCA', '2026-07-01', '2026-07-01T00:00:00', 1, '{}')"
    )
    conn.commit()
    conn.close()

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM candidate_observations_quarantine WHERE ticker = 'BBCA'"
        ).fetchone()
    assert row["config_hash"] is None
    assert row["workflow"] is None
    assert row["window_sessions"] is None


def test_apply_works_when_source_table_has_no_id_column(tmp_path: Path):
    """Regression test: an even-older schema than the AUTOINCREMENT `id`
    migration has no `id` column and no `config_hash` column at all. Repair
    identity must come from SQLite `rowid`, not the optional `id` column, or
    apply crashes with IndexError/KeyError when building the delete."""
    db_path = tmp_path / "no_id_schema.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE candidate_observations (
            ticker         TEXT NOT NULL,
            snapshot_date  TEXT NOT NULL,
            captured_at    TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json   TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json) "
        "VALUES ('BBCA', '2026-07-01', '2026-07-01T00:00:00', 1, '{}')"
    )
    conn.commit()
    conn.close()

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0]
    assert remaining == 0

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM candidate_observations_quarantine WHERE ticker = 'BBCA'"
        ).fetchone()
    assert row["id"] is None
    assert row["config_hash"] is None
    assert row["source_row_id"] is not None
