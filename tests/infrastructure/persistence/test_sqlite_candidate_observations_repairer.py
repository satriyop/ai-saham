"""Tests for SQLiteCandidateObservationsRepairer (DQ-001J)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
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
    schema_version = CANDIDATE_OBSERVATION_SCHEMA_VERSION if config_hash != "" else 1
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


# ── ARTIFACT-IDENTITY Slice 3: identity columns in quarantine ─────────────────


def _identity_row(
    db_path: Path,
    *,
    ticker: str = "BBCA",
    snapshot_date: str = "2026-07-01",
    config_hash: str = "",
) -> int:
    """Insert a candidate_observation row with a non-empty artifact identity
    and return the row id."""
    schema_version = CANDIDATE_OBSERVATION_SCHEMA_VERSION if config_hash != "" else 1
    identity = SignalArtifactIdentity(
        artifact_id=ArtifactId(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        semantic_compatibility_id=SemanticCompatibilityId(
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        provenance=ArtifactProvenance(
            application_revision="abc1234",
            complete_config_hash="c" * 64,
            complete_authority_registry_hash="d" * 64,
            universe_snapshot_id="univ-001",
            idx_calendar_version="2026-v3",
            session_rule_version="sr-v2",
            decision_at=datetime(2026, 7, 3, 16, 0, 0, tzinfo=timezone.utc),
            captured_at=datetime(2026, 7, 3, 9, 30, 0, tzinfo=timezone.utc),
            latest_completed_session=date(2026, 7, 3),
            analysis_as_of=date(2026, 7, 3),
            sources=(
                ArtifactSourceProvenance(
                    source_family="exchange",
                    provider="idx",
                    source_snapshot_id="snap-001",
                    observed_through=date(2026, 7, 3),
                    available_at=datetime(2026, 7, 3, 7, 0, 0, tzinfo=timezone.utc),
                    cutoff_at=datetime(2026, 7, 3, 8, 0, 0, tzinfo=timezone.utc),
                ),
            ),
        ),
    )
    from src.infrastructure.persistence.sqlite_signal_artifact_identity_codec import (
        encode_signal_artifact_identity,
    )

    aid, scid, pj = encode_signal_artifact_identity(identity)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json,
             config_hash, artifact_id, semantic_compatibility_id,
             artifact_provenance_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            snapshot_date,
            f"{snapshot_date}T00:00:00",
            schema_version,
            "{}",
            config_hash,
            aid,
            scid,
            pj,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def test_quarantine_preserves_identity_columns(tmp_path: Path):
    """When a legacy row with a non-empty artifact identity is quarantined,
    all three identity columns must round-trip into the quarantine table."""
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _identity_row(db_path, ticker="LEGACY1", config_hash="")

    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM candidate_observations_quarantine WHERE ticker = 'LEGACY1'"
        ).fetchone()
    assert row is not None
    assert row["artifact_id"] is not None
    assert row["semantic_compatibility_id"] is not None
    assert row["artifact_provenance_json"] is not None
    assert "sha256:" in row["artifact_id"]
    assert "sha256:" in row["semantic_compatibility_id"]


def test_existing_quarantine_table_is_upgraded(tmp_path: Path):
    """A quarantine table created before the identity columns existed must be
    upgraded by ensure_quarantine_table() before identity-bearing rows are
    copied."""
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _identity_row(db_path, ticker="LEGACY1", config_hash="")

    # Create quarantine table with all columns EXCEPT the 3 identity columns
    # (simulating the schema before ARTIFACT-IDENTITY Slice 3)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_observations_quarantine (
            quarantine_id                INTEGER PRIMARY KEY AUTOINCREMENT,
            source_row_id                INTEGER NOT NULL,
            id                          INTEGER,
            ticker                      TEXT,
            snapshot_date               TEXT,
            captured_at                 TEXT,
            schema_version              INTEGER,
            payload_json                TEXT,
            workflow                    TEXT,
            window_sessions             INTEGER,
            data_as_of_date             TEXT,
            config_hash                 TEXT,
            decision_at                 TEXT,
            latest_completed_session    TEXT,
            analysis_as_of              TEXT,
            market_session_name         TEXT,
            is_eod_pending               INTEGER,
            resolution_source           TEXT,
            resolution_notes_json       TEXT,
            quarantine_reason           TEXT NOT NULL,
            quarantined_at              TEXT NOT NULL,
            repair_run_id                TEXT NOT NULL,
            original_table               TEXT NOT NULL DEFAULT 'candidate_observations',
            quarantine_schema_version    INTEGER NOT NULL DEFAULT 1,
            UNIQUE(source_row_id)
        )
        """
    )
    conn.commit()
    conn.close()

    # Verify identity columns are missing before upgrade
    with sqlite3.connect(str(db_path)) as conn:
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM pragma_table_info('candidate_observations_quarantine')"
            )
        }
    assert "artifact_id" not in cols
    assert "semantic_compatibility_id" not in cols
    assert "artifact_provenance_json" not in cols

    # Upgrade + quarantine
    repairer = _make_repairer(db_path)
    repairer.ensure_quarantine_table()
    quarantined, deleted = repairer.quarantine_and_delete_legacy(_REPAIR_RUN_ID)

    assert quarantined == 1
    assert deleted == 1

    # Verify identity columns now exist and are populated
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM candidate_observations_quarantine WHERE ticker = 'LEGACY1'"
        ).fetchone()
    assert row is not None
    assert row["artifact_id"] is not None
    assert row["semantic_compatibility_id"] is not None
    assert row["artifact_provenance_json"] is not None
