"""Tests for SQLiteCandidateObservationIdentityReader (DQ-001I)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from src.application.use_case.audit_candidate_observation_identity_use_case import (
    RawCandidateObservationIdentityData,
)
from src.infrastructure.persistence.sqlite_candidate_observation_identity_reader import (
    SQLiteCandidateObservationIdentityReader,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE candidate_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            workflow TEXT NOT NULL DEFAULT '',
            window_sessions INTEGER NOT NULL DEFAULT 0,
            data_as_of_date TEXT NOT NULL DEFAULT '',
            config_hash TEXT NOT NULL DEFAULT ''
        )
    """)


def _insert(
    conn: sqlite3.Connection,
    ticker: str = "BBCA",
    snapshot_date: str = "2026-07-15",
    captured_at: str = "2026-07-15T00:00:00+00:00",
    config_hash: str = "",
    workflow: str = "accumulation_screen",
    window_sessions: int = 30,
    data_as_of_date: str = "2026-07-15",
) -> None:
    if config_hash is None:
        config_hash = ""
    schema_version = 2 if config_hash != "" else 1
    conn.execute(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, "
        "workflow, window_sessions, data_as_of_date, config_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ticker,
            snapshot_date,
            captured_at,
            schema_version,
            f'{{"schema_version": {schema_version}}}',
            workflow,
            window_sessions,
            data_as_of_date,
            config_hash,
        ),
    )


def _make_reader(db_path: Path) -> SQLiteCandidateObservationIdentityReader:
    return SQLiteCandidateObservationIdentityReader(db_path)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestDatabaseExistence:
    def test_missing_db_returns_not_exists(self):
        reader = _make_reader(Path("/tmp/nonexistent/foo.db"))
        assert reader.database_exists() is False
        data = reader.observe_candidate_observation_identity()
        assert data.exists is False

    def test_missing_db_does_not_create_file(self):
        path = Path("/tmp/nonexistent_do_not_create.db")
        reader = _make_reader(path)
        reader.observe_candidate_observation_identity()
        assert not path.exists()

    def test_missing_table_returns_not_exists(self, tmp_path: Path):
        db_path = tmp_path / "empty.db"
        sqlite3.connect(str(db_path)).close()

        reader = _make_reader(db_path)
        assert reader.database_exists() is True
        data = reader.observe_candidate_observation_identity()
        assert data.exists is False


class TestReadOnlyGuarantee:
    def test_opens_in_read_only_mode(self, tmp_path: Path):
        db_path = tmp_path / "ro_test.db"
        conn = sqlite3.connect(str(db_path))
        _create_table(conn)
        conn.close()

        reader = _make_reader(db_path)
        data = reader.observe_candidate_observation_identity()
        assert data.exists is True

    def test_does_not_mutate_database(self, tmp_path: Path):
        db_path = tmp_path / "no_mutate.db"
        conn = sqlite3.connect(str(db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA")
        conn.commit()
        conn.close()

        mtime_before = db_path.stat().st_mtime_ns
        time.sleep(0.01)

        reader = _make_reader(db_path)
        reader.observe_candidate_observation_identity()

        mtime_after = db_path.stat().st_mtime_ns
        assert mtime_before == mtime_after


class TestAggregateCounts:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "agg.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", config_hash="abc123", captured_at="2026-07-15T01:00:00+00:00")
        _insert(conn, ticker="BBRI", config_hash="def456", captured_at="2026-07-15T02:00:00+00:00")
        _insert(conn, ticker="TLKM", config_hash="", captured_at="2026-07-14T01:00:00+00:00")
        _insert(conn, ticker="UNVR", config_hash="", captured_at="2026-07-13T01:00:00+00:00",
                snapshot_date="2026-07-13")
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_total_row_count(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.total_row_count == 4

    def test_canonical_and_legacy_counts(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.canonical_row_count == 2
        assert data.legacy_row_count == 2

    def test_snapshot_date_range(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.snapshot_date_min == "2026-07-13"
        assert data.snapshot_date_max == "2026-07-15"

    def test_captured_at_range(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.captured_at_min == "2026-07-13T01:00:00+00:00"
        assert data.captured_at_max == "2026-07-15T02:00:00+00:00"


class TestMissingIdentityCounts:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "missing_identity.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", config_hash="abc")
        _insert(conn, ticker="BBRI", config_hash="")
        _insert(conn, ticker="TLKM", config_hash="def", window_sessions=0)
        _insert(conn, ticker="UNVR", config_hash="ghi", workflow="")
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_config_hash_missing(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.missing_identity_counts["config_hash"] == 1

    def test_workflow_missing(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.missing_identity_counts["workflow"] == 1

    def test_window_sessions_missing(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.missing_identity_counts["window_sessions"] == 1

    def test_data_as_of_date_missing(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.missing_identity_counts["data_as_of_date"] == 0


class TestWorkflowAndWindowCounts:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "dist.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", config_hash="a", workflow="accumulation_screen", window_sessions=30)
        _insert(conn, ticker="BBRI", config_hash="b", workflow="accumulation_screen", window_sessions=30)
        _insert(conn, ticker="TLKM", config_hash="c", workflow="swing_analysis", window_sessions=7)
        _insert(conn, ticker="UNVR", config_hash="d", workflow="swing_analysis", window_sessions=7)
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_workflow_counts(self):
        data = self.reader.observe_candidate_observation_identity()
        wf_map = {w["workflow"]: w["row_count"] for w in data.workflow_counts}
        assert wf_map.get("accumulation_screen") == 2
        assert wf_map.get("swing_analysis") == 2

    def test_window_session_counts(self):
        data = self.reader.observe_candidate_observation_identity()
        ws_map = {w["window_sessions"]: w["row_count"] for w in data.window_session_counts}
        assert ws_map.get(30) == 2
        assert ws_map.get(7) == 2


class TestLegacyBySnapshotDate:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "legacy_date.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", snapshot_date="2026-07-15", config_hash="")
        _insert(conn, ticker="BBRI", snapshot_date="2026-07-15", config_hash="")
        _insert(conn, ticker="TLKM", snapshot_date="2026-07-14", config_hash="")
        _insert(conn, ticker="UNVR", snapshot_date="2026-07-14", config_hash="abc")
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_legacy_by_snapshot_date_counts(self):
        data = self.reader.observe_candidate_observation_identity()
        legacy_map = {r["snapshot_date"]: r["row_count"] for r in data.legacy_by_snapshot_date}
        assert legacy_map.get("2026-07-15") == 2
        assert legacy_map.get("2026-07-14") == 1


class TestDuplicateIdentity:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "dup.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        # Two canonical rows with identical identity
        _insert(conn, ticker="BBCA", config_hash="aaa", workflow="swing_analysis", window_sessions=7)
        _insert(conn, ticker="BBCA", config_hash="aaa", workflow="swing_analysis", window_sessions=7,
                captured_at="2026-07-15T01:00:01+00:00")
        # One more canonical with unique identity
        _insert(conn, ticker="BBRI", config_hash="bbb", workflow="accumulation_screen", window_sessions=30)
        # Legacy rows (ignored in duplicate counts)
        _insert(conn, ticker="TLKM", config_hash="")
        _insert(conn, ticker="UNVR", config_hash="")
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_duplicate_group_count(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.duplicate_identity_group_count == 1

    def test_duplicate_row_count(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.duplicate_identity_row_count == 2

    def test_legacy_rows_ignored_in_duplicate_count(self):
        data = self.reader.observe_candidate_observation_identity()
        legacy_only = [r for r in data.legacy_by_snapshot_date if r["row_count"] > 0]
        assert len(legacy_only) <= 2


class TestNullEmptyWhitespaceLegacy:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "legacy_def.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", config_hash="")  # empty → legacy
        _insert(conn, ticker="BBRI", config_hash=None)  # null → legacy
        _insert(conn, ticker="TLKM", config_hash="  ")  # whitespace → legacy
        _insert(conn, ticker="UNVR", config_hash="abc123")  # non-empty → canonical
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_whitespace_config_hash_is_legacy(self):
        data = self.reader.observe_candidate_observation_identity()
        assert data.legacy_row_count == 3
        assert data.canonical_row_count == 1


class TestLatestReadinessDependency:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path: Path):
        self.db_path = tmp_path / "latest_dep.db"
        conn = sqlite3.connect(str(self.db_path))
        _create_table(conn)
        # Latest date has mixed
        _insert(conn, ticker="BBCA", snapshot_date="2026-07-15", config_hash="abc")
        _insert(conn, ticker="BBRI", snapshot_date="2026-07-15", config_hash="")
        _insert(conn, ticker="TLKM", snapshot_date="2026-07-14", config_hash="def")
        conn.commit()
        conn.close()
        self.reader = _make_reader(self.db_path)

    def test_latest_date_has_mixed_legacy(self):
        data = self.reader.observe_candidate_observation_identity()
        dep = data.latest_readiness_dependency
        assert dep["latest_snapshot_date"] == "2026-07-15"
        assert dep["latest_total_rows"] == 2
        assert dep["latest_legacy_rows"] == 1
        assert dep["latest_canonical_rows"] == 1
        assert dep["depends_on_legacy"] is True

    def test_latest_date_all_canonical(self, tmp_path: Path):
        db_path = tmp_path / "latest_all_canonical.db"
        conn = sqlite3.connect(str(db_path))
        _create_table(conn)
        _insert(conn, ticker="BBCA", snapshot_date="2026-07-15", config_hash="abc")
        _insert(conn, ticker="BBRI", snapshot_date="2026-07-15", config_hash="def")
        _insert(conn, ticker="TLKM", snapshot_date="2026-07-14", config_hash="")
        conn.commit()
        conn.close()

        reader = _make_reader(db_path)
        data = reader.observe_candidate_observation_identity()
        dep = data.latest_readiness_dependency
        assert dep["latest_snapshot_date"] == "2026-07-15"
        assert dep["latest_legacy_rows"] == 0
        assert dep["depends_on_legacy"] is False


class TestMissingColumnHandling:
    def test_missing_config_hash_counts_all_as_legacy(self, tmp_path: Path):
        db_path = tmp_path / "missing_config.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE candidate_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                workflow TEXT NOT NULL DEFAULT '',
                window_sessions INTEGER NOT NULL DEFAULT 0,
                data_as_of_date TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute(
            "INSERT INTO candidate_observations "
            "(ticker, snapshot_date, captured_at, schema_version, payload_json) "
            "VALUES ('BBCA', '2026-07-15', '2026-07-15T00:00:00+00:00', 1, '{}')"
        )
        conn.execute(
            "INSERT INTO candidate_observations "
            "(ticker, snapshot_date, captured_at, schema_version, payload_json) "
            "VALUES ('BBRI', '2026-07-14', '2026-07-14T00:00:00+00:00', 1, '{}')"
        )
        conn.commit()
        conn.close()

        reader = _make_reader(db_path)
        data = reader.observe_candidate_observation_identity()
        assert data.exists is True
        assert data.total_row_count == 2
        assert data.canonical_row_count == 0
        assert data.legacy_row_count == 2
        assert "config_hash" in data.missing_columns
        assert data.missing_identity_counts["config_hash"] == 2
        dep = data.latest_readiness_dependency
        assert dep["depends_on_legacy"] is True
        assert dep["latest_legacy_rows"] == dep["latest_total_rows"]

    def test_partial_missing_column(self, tmp_path: Path):
        db_path = tmp_path / "partial_missing.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE candidate_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                config_hash TEXT NOT NULL DEFAULT '',
                window_sessions INTEGER NOT NULL DEFAULT 0,
                data_as_of_date TEXT NOT NULL DEFAULT ''
            )
        """)
        # No workflow column
        conn.execute(
            "INSERT INTO candidate_observations "
            "(ticker, snapshot_date, captured_at, schema_version, payload_json) "
            "VALUES ('BBCA', '2026-07-15', '2026-07-15T00:00:00+00:00', 1, '{}')"
        )
        conn.commit()
        conn.close()

        reader = _make_reader(db_path)
        data = reader.observe_candidate_observation_identity()
        assert data.exists is True
        assert "workflow" in data.missing_columns
        assert data.missing_identity_counts["workflow"] == 1
