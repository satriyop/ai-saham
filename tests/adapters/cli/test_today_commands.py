"""Tests for the daily briefing CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_today_renders_rich_dashboard_with_lifecycle_next_steps(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "today",
            "--universe",
            "lq45",
            "--date",
            "2026-06-19",
            "--db",
            str(tmp_path / "market.db"),
        ],
    )

    assert result.exit_code == 0
    assert "Daily Briefing - 2026-06-19" in result.stdout
    assert "Data & Regime" in result.stdout
    assert "Top Pre-Open Candidates" in result.stdout
    assert "Top Accumulation Candidates" in result.stdout
    assert "Run: saham learn snapshot --force" in result.stdout
    assert "Next: saham screen accum --universe lq45 | saham analyze swing TICKER" in result.stdout
