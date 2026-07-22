"""DQ-011 — thin CLI contracts for `saham research signal replay`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

runner = CliRunner()


def _count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _init_signal_tables(db_path: Path) -> None:
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)


def test_signal_replay_rejects_invalid_date(tmp_path):
    db_path = tmp_path / "replay.db"
    _init_signal_tables(db_path)

    result = runner.invoke(
        app,
        ["research", "signal", "replay", "BBCA", "not-a-date", "--db", str(db_path)],
    )

    assert result.exit_code == 1
    assert "Invalid date" in result.stderr
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0


def test_signal_replay_not_found_is_read_only(tmp_path):
    db_path = tmp_path / "replay.db"
    _init_signal_tables(db_path)

    result = runner.invoke(
        app,
        ["research", "signal", "replay", "BBCA", "2026-07-03", "--db", str(db_path)],
    )

    assert result.exit_code == 1
    assert "[error]" in result.stderr
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0


def test_signal_replay_verify_not_found_is_read_only(tmp_path):
    db_path = tmp_path / "replay.db"
    _init_signal_tables(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "replay",
            "BBCA",
            "2026-07-03",
            "--verify",
            "--db",
            str(db_path),
        ],
    )

    # Verify path maps UNREPRODUCIBLE (including observation_not_found) to exit 2.
    assert result.exit_code == 2
    assert "UNREPRODUCIBLE" in result.output
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0
