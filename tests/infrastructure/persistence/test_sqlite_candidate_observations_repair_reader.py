"""Tests for SQLiteCandidateObservationsRepairReader (DQ-001J)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repair_reader import (
    SQLiteCandidateObservationsRepairReader,
)


def _build_schema(db_path: Path) -> None:
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )

    SQLiteCandidateObservationsRepository(db_path)


def _insert_row(
    db_path: Path,
    *,
    ticker: str,
    snapshot_date: str,
    config_hash: str = "",
    workflow: str = "",
    window_sessions: int = 0,
    data_as_of_date: str = "",
) -> None:
    schema_version = CANDIDATE_OBSERVATION_SCHEMA_VERSION if config_hash != "" else 1
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json,
             workflow, window_sessions, data_as_of_date, config_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            snapshot_date,
            f"{snapshot_date}T00:00:00",
            schema_version,
            "{}",
            workflow,
            window_sessions,
            data_as_of_date,
            config_hash,
        ),
    )
    conn.commit()
    conn.close()


def _make_reader(db_path: Path) -> SQLiteCandidateObservationsRepairReader:
    return SQLiteCandidateObservationsRepairReader(db_path)


# ── database/table existence ─────────────────────────────────────────────────


def test_missing_database_reports_not_exists(tmp_path: Path):
    reader = _make_reader(tmp_path / "does_not_exist.db")

    assert reader.database_exists() is False


def test_missing_database_does_not_create_file(tmp_path: Path):
    db_path = tmp_path / "does_not_exist.db"
    reader = _make_reader(db_path)

    reader.observe_repair_state()

    assert not db_path.exists()


def test_missing_table_returns_source_unavailable(tmp_path: Path):
    db_path = tmp_path / "no_table.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    reader = _make_reader(db_path)

    assert reader.database_exists() is True
    state = reader.observe_repair_state()
    assert state.exists is False


# ── legacy/canonical counts ──────────────────────────────────────────────────


def test_legacy_and_canonical_counts_are_correct(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="BBCA", snapshot_date="2026-07-01", config_hash="")
    _insert_row(
        db_path,
        ticker="BBRI",
        snapshot_date="2026-07-01",
        config_hash="abc123",
        workflow="eod",
        window_sessions=1,
        data_as_of_date="2026-07-01",
    )

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.exists is True
    assert state.total_row_count == 2
    assert state.legacy_row_count == 1
    assert state.canonical_row_count == 1


def test_config_hash_empty_and_whitespace_are_both_legacy(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="AAAA", snapshot_date="2026-07-01", config_hash="")
    _insert_row(db_path, ticker="BBBB", snapshot_date="2026-07-01", config_hash="   ")

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.legacy_row_count == 2
    assert state.canonical_row_count == 0


def test_missing_config_hash_column_treats_all_rows_as_legacy(tmp_path: Path):
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

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.exists is True
    assert state.total_row_count == 1
    assert state.legacy_row_count == 1
    assert state.canonical_row_count == 0
    assert "config_hash" in state.missing_columns
    assert state.latest_legacy_row_count == 1
    assert state.latest_canonical_row_count == 0


def test_missing_snapshot_date_column_does_not_crash(tmp_path: Path):
    """Regression test: an even-older/malformed schema without snapshot_date
    must not crash MIN/MAX/GROUP BY queries — those must be skipped entirely
    when the column is missing."""
    db_path = tmp_path / "no_snapshot_date_schema.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE candidate_observations (
            ticker       TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO candidate_observations (ticker, payload_json) VALUES ('BBCA', '{}')"
    )
    conn.commit()
    conn.close()

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.exists is True
    assert state.total_row_count == 1
    assert "snapshot_date" in state.missing_columns
    assert state.snapshot_date_min is None
    assert state.snapshot_date_max is None
    assert state.latest_snapshot_date is None
    # config_hash is also missing here, so every row is legacy; with no
    # snapshot_date to group by, the whole table is treated as "latest".
    assert state.legacy_row_count == 1
    assert state.latest_legacy_row_count == 1
    assert state.latest_canonical_row_count == 0


# ── dry-run / no mutation ────────────────────────────────────────────────────


def test_reader_never_mutates_database(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="BBCA", snapshot_date="2026-07-01", config_hash="")

    mtime_before = db_path.stat().st_mtime_ns
    reader = _make_reader(db_path)
    reader.observe_repair_state()

    assert db_path.stat().st_mtime_ns == mtime_before


def test_reader_opens_read_only(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="BBCA", snapshot_date="2026-07-01", config_hash="")

    reader = _make_reader(db_path)
    conn = reader._connect()
    try:
        import pytest

        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM candidate_observations")
    finally:
        conn.close()


# ── latest snapshot dependency ───────────────────────────────────────────────


def test_latest_snapshot_dependency_reports_legacy_and_canonical(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schema(db_path)
    _insert_row(db_path, ticker="AAAA", snapshot_date="2026-07-01", config_hash="hash1")
    _insert_row(db_path, ticker="BBBB", snapshot_date="2026-07-15", config_hash="")
    _insert_row(db_path, ticker="CCCC", snapshot_date="2026-07-15", config_hash="hash2")

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.latest_snapshot_date == "2026-07-15"
    assert state.latest_legacy_row_count == 1
    assert state.latest_canonical_row_count == 1
    assert state.snapshot_date_min == "2026-07-01"
    assert state.snapshot_date_max == "2026-07-15"
