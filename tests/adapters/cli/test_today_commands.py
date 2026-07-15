"""Tests for the daily briefing CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_cli_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "today" in result.stdout


def test_today_help_exits_zero():
    result = runner.invoke(app, ["today", "--help"])
    assert result.exit_code == 0
    assert "--universe" in result.stdout
    assert "--date" in result.stdout
    assert "--db" in result.stdout


def test_today_shows_market_source_tag(tmp_path: Path):
    from datetime import datetime
    from unittest.mock import patch

    from src.domain.value_objects.market_status import MarketStatus

    fake_status = MarketStatus(
        status="STATUS_OPEN",
        session_name="Regular",
        is_open=True,
        session_open="09:00",
        session_close="15:00",
        fetched_at=datetime.now(),
        source="test_source",
    )

    with patch(
        "src.infrastructure.browser.stockbit_market_time.get_display_market_status",
        return_value=fake_status,
    ):
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
    assert "[test_source]" in result.stdout


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
    stdout_clean = result.stdout.replace("\n", "").replace(" ", "").replace("│", "")
    assert "sahamscreenaccum--universelq45|sahamanalyzeswingTICKER" in stdout_clean


def test_today_uses_loaded_config_and_not_global(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    from src.adapters.cli.today_commands import today
    with patch("src.adapters.cli.today_commands.load_accumulation_screener_config") as mock_load, \
         patch("src.adapters.cli.today_commands.DailyBriefingUseCase") as mock_uc_class:
        mock_cfg = MagicMock()
        mock_cfg.derived_features = MagicMock()
        mock_load.return_value = mock_cfg

        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc
        mock_response = mock_uc.execute.return_value
        mock_response.universe = "lq45"
        mock_response.universe_count = 0
        mock_response.stale_count = 0
        mock_response.regime = None
        mock_response.pre_open = []
        mock_response.accumulation = []
        mock_response.watchlist_triggers = []
        mock_response.lifecycle_suggestions = []

        today(universe="lq45", date_str="2026-06-19", db_path=tmp_path / "market.db")

        mock_load.assert_called_once()
