"""CLI: research pre-open status late_capture miss reason."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

runner = CliRunner()
WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)


def test_status_json_and_human_echo_late_capture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "s.db"
    SQLiteLearningArtifactRepository(db_path)
    IEVJsonSidecarWriter().write_snapshot(
        SESSION,
        [MoverData("BBCA", 100_000, 5900)],
        captured_at=datetime(2026, 6, 18, 9, 24, 24, tzinfo=WIB),
        top_n=50,
    )

    json_result = runner.invoke(
        app,
        [
            "research",
            "pre-open",
            "status",
            "--session",
            SESSION.isoformat(),
            "--db",
            str(db_path),
            "--format",
            "json",
        ],
    )
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.stdout)
    assert payload["observation_count"] == 0
    assert payload["miss_reason"] == "late_capture"
    assert any("late_capture" in action for action in payload["next_actions"])

    table_result = runner.invoke(
        app,
        [
            "research",
            "pre-open",
            "status",
            "--session",
            SESSION.isoformat(),
            "--db",
            str(db_path),
        ],
    )
    assert table_result.exit_code == 0, table_result.output
    assert "miss_reason: late_capture" in table_result.stdout
    assert "late_capture" in table_result.stdout
