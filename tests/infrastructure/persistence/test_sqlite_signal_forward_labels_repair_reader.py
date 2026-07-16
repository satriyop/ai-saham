"""Tests for SQLiteSignalForwardLabelsRepairReader (DQ-001L)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_signal_forward_labels_repair_reader import (
    SQLiteSignalForwardLabelsRepairReader,
)


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
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
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
    conn.close()


def _make_reader(db_path: Path) -> SQLiteSignalForwardLabelsRepairReader:
    return SQLiteSignalForwardLabelsRepairReader(db_path)


# ── database/table existence ─────────────────────────────────────────────────


def test_missing_database_reports_not_exists(tmp_path: Path):
    reader = _make_reader(tmp_path / "does_not_exist.db")
    assert reader.database_exists() is False


def test_missing_database_does_not_create_file(tmp_path: Path):
    db_path = tmp_path / "does_not_exist.db"
    reader = _make_reader(db_path)
    state = reader.observe_repair_state()
    assert not db_path.exists()
    assert state.exists is False


def test_missing_signal_forward_labels_table_returns_source_unavailable(
    tmp_path: Path,
):
    db_path = tmp_path / "no_sfl.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()
    assert state.exists is False


def test_missing_candidate_observations_table_returns_source_unavailable(
    tmp_path: Path,
):
    db_path = tmp_path / "no_co.db"
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    SQLiteSignalForwardLabelsRepository(db_path)

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()
    assert state.exists is True
    assert state.source_unavailable is True
    assert state.source_unavailable_reason == "CANDIDATE_OBSERVATIONS_TABLE_MISSING"


# ── missing join columns ─────────────────────────────────────────────────────


def test_missing_sfl_join_column_returns_required_linkage_columns_missing(
    tmp_path: Path,
):
    db_path = tmp_path / "no_sfl_col.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candidate_observations ("
        "ticker TEXT NOT NULL, snapshot_date TEXT NOT NULL, "
        "captured_at TEXT NOT NULL, schema_version INTEGER NOT NULL, "
        "payload_json TEXT NOT NULL, config_hash TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE signal_forward_labels ("
        "ticker TEXT NOT NULL, horizon TEXT NOT NULL, "
        "outcome_label TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()
    assert state.exists is True
    assert state.source_unavailable is True
    assert state.source_unavailable_reason == "REQUIRED_LINKAGE_COLUMNS_MISSING"
    assert "signal_date" in state.missing_columns


def test_missing_co_join_column_returns_required_linkage_columns_missing(
    tmp_path: Path,
):
    db_path = tmp_path / "no_co_col.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candidate_observations ("
        "ticker TEXT NOT NULL, captured_at TEXT NOT NULL, "
        "schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL, "
        "config_hash TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE signal_forward_labels ("
        "ticker TEXT NOT NULL, signal_date TEXT NOT NULL, "
        "horizon TEXT NOT NULL, observation_captured_at TEXT NOT NULL, "
        "outcome_label TEXT NOT NULL, fingerprint_json TEXT NOT NULL, "
        "schema_version INTEGER NOT NULL, created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()
    assert state.exists is True
    assert state.source_unavailable is True
    assert state.source_unavailable_reason == "REQUIRED_LINKAGE_COLUMNS_MISSING"
    assert "snapshot_date" in state.missing_columns


# ── orphan / canonical counts ────────────────────────────────────────────────


def test_orphan_and_canonical_counts_are_correct(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")  # canonical
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-02")  # orphan

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.exists is True
    assert state.total_row_count == 2
    assert state.orphan_row_count == 1
    assert state.canonical_row_count == 1


def test_all_orphan_when_no_candidate_observations_match(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.total_row_count == 1
    assert state.orphan_row_count == 1
    assert state.canonical_row_count == 0


def test_no_orphans_when_all_match(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_co_row(db_path, ticker="BBCA", snapshot_date="2026-07-01")
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.total_row_count == 1
    assert state.orphan_row_count == 0
    assert state.canonical_row_count == 1


def test_zero_rows_returns_zero_counts(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.exists is True
    assert state.total_row_count == 0
    assert state.orphan_row_count == 0
    assert state.canonical_row_count == 0
    assert state.signal_date_min is None
    assert state.signal_date_max is None


# ── date range ────────────────────────────────────────────────────────────────


def test_date_range_is_correct(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-01-02")
    _insert_label_row(db_path, ticker="BBRI", signal_date="2026-06-15")

    reader = _make_reader(db_path)
    state = reader.observe_repair_state()

    assert state.signal_date_min == "2026-01-02"
    assert state.signal_date_max == "2026-06-15"


# ── no mutation / read-only ──────────────────────────────────────────────────


def test_reader_never_mutates_database(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")

    mtime_before = db_path.stat().st_mtime_ns
    reader = _make_reader(db_path)
    reader.observe_repair_state()

    assert db_path.stat().st_mtime_ns == mtime_before


def test_reader_opens_read_only(tmp_path: Path):
    db_path = tmp_path / "data.db"
    _build_schemas(db_path)
    _insert_label_row(db_path, ticker="BBCA", signal_date="2026-07-01")

    reader = _make_reader(db_path)
    conn = reader._connect()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM signal_forward_labels")
    finally:
        conn.close()
