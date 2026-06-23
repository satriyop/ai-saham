"""Tests for IEV fetch CLI command."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli import fetch_iev_commands
from src.adapters.cli.main import app
from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

runner = CliRunner()


def test_fetch_iev_help_is_registered():
    result = runner.invoke(app, ["fetch", "iev", "--help"])

    assert result.exit_code == 0
    assert "Capture today's IEV mover ranking" in result.stdout
    assert "--top-n" in result.stdout


def test_fetch_iev_writes_sqlite_and_json_sidecar(monkeypatch, tmp_path: Path):
    from src.infrastructure.browser import playwright_stockbit_provider as playwright_stockbit

    class FakeStockbitProvider:
        def __init__(self, headless: bool = True) -> None:
            self.headless = headless

        def fetch_iev_snapshot(self, top_n: int):
            assert top_n == 5
            return [
                MoverData("BBCA", 500_000, 5900),
                MoverData("BBRI", 400_000, 3100),
            ]

    fixed_now = datetime(2026, 6, 19, 8, 57, 3, tzinfo=ZoneInfo("Asia/Jakarta"))
    monkeypatch.setattr(playwright_stockbit, "PlaywrightStockbitProvider", FakeStockbitProvider)
    monkeypatch.setattr(fetch_iev_commands, "_current_idx_datetime", lambda: fixed_now)
    monkeypatch.chdir(tmp_path)

    db_path = tmp_path / "iev.db"
    result = runner.invoke(app, ["fetch", "iev", "--top-n", "5", "--db", str(db_path)])

    assert result.exit_code == 0, result.output

    repo = SQLiteIEVRepository(db_path)
    snapshot = repo.get_snapshot(fixed_now.date())
    assert [row.ticker for row in snapshot] == ["BBCA", "BBRI"]

    sidecar_path = tmp_path / "data" / "iev" / "20260619" / "iev.json"
    assert sidecar_path.exists()
    payload = json.loads(sidecar_path.read_text())
    assert payload["captured_at"] == "2026-06-19T08:57:03+07:00"
    assert payload["snapshot_date"] == "2026-06-19"
    assert payload["top_n"] == 5
    assert payload["count"] == 2
    assert payload["movers"][0] == {
        "rank": 1,
        "ticker": "BBCA",
        "iev": 500_000,
        "iep": 5900,
    }
