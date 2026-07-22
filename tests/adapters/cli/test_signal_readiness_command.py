"""DQ-011 — thin CLI contracts for `saham research signal readiness`."""

from __future__ import annotations

import json
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

TARGET = "foreign_institutional_accumulation_large_cap_SWING_10D"


def _count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _init_signal_tables(db_path: Path) -> None:
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)


def test_signal_readiness_rejects_invalid_target(tmp_path):
    db_path = tmp_path / "readiness.db"
    _init_signal_tables(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "readiness",
            "--target",
            "not-a-valid-target",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid target" in result.stderr
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0


def test_signal_readiness_json_empty_db_is_read_only(tmp_path):
    db_path = tmp_path / "readiness.db"
    _init_signal_tables(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "readiness",
            "--target",
            TARGET,
            "--format",
            "json",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["target"] == TARGET
    assert payload["is_oos"]["promotion_eligible"] is False
    assert "exclusions" in payload
    assert "notes" in payload
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0
