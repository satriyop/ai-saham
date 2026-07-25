"""Tests for additive lifecycle CLI command groups."""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_root_help_shows_lifecycle_groups():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "today" in result.stdout
    assert "fetch" in result.stdout
    assert "screen" in result.stdout
    assert "research" in result.stdout
    assert "view" in result.stdout
    assert "learn" not in result.stdout
    assert "│ data" not in result.stdout
    assert "│ skill" not in result.stdout


def test_fetch_group_exposes_ingestion_commands():
    result = runner.invoke(app, ["fetch", "--help"])

    assert result.exit_code == 0
    assert "market" in result.stdout
    assert "broker" in result.stdout
    assert "broker-import" in result.stdout
    assert "broker-history" in result.stdout
    assert "broker-top-foreign" in result.stdout
    assert "iev" in result.stdout
    assert "stockbit" in result.stdout
    assert "universe" in result.stdout


def test_screen_group_exposes_discovery_commands():
    result = runner.invoke(app, ["screen", "--help"])

    assert result.exit_code == 0
    assert "pre-open" in result.stdout
    assert "accum" in result.stdout


def test_removed_legacy_data_group_is_not_callable():
    result = runner.invoke(app, ["data", "--help"])

    assert result.exit_code != 0


def test_learn_group_removed_clean_break():
    result = runner.invoke(app, ["learn", "--help"])

    assert result.exit_code != 0


def test_research_pre_open_exposes_session_and_corpus_commands():
    result = runner.invoke(app, ["research", "pre-open", "--help"])

    assert result.exit_code == 0
    assert "capture" in result.stdout
    assert "labels" in result.stdout
    assert "track" in result.stdout
    assert "grade" in result.stdout
    assert "prompt" in result.stdout
    assert "tune" in result.stdout


def test_view_group_exposes_ticker_dashboard_command():
    result = runner.invoke(app, ["view", "--help"])

    assert result.exit_code == 0
    assert "ticker" in result.stdout
    assert "saham view BBCA" in result.stdout
    assert "universe" in result.stdout
    assert "broker" in result.stdout


def test_view_broker_group_exposes_read_only_commands():
    result = runner.invoke(app, ["view", "broker", "--help"])

    assert result.exit_code == 0
    for cmd in (
    "show",
    "top-stocks",
    "flow",
    "history",
    "status",
    "top-foreign",
    "mappings",
    "list",
):
        assert cmd in result.stdout


def test_analyze_swing_is_available():
    result = runner.invoke(app, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "swing" in result.stdout


def test_deprecated_save_session_path_is_removed():
    result = runner.invoke(app, ["trade", "intraday", "--help"])

    assert result.exit_code != 0


def test_trade_group_exposes_shallow_workspace_commands():
    result = runner.invoke(app, ["trade", "--help"])

    assert result.exit_code == 0
    assert "confirm" in result.stdout
    assert "log" in result.stdout
    assert "review" in result.stdout
    assert "outcome" in result.stdout
    assert "size" in result.stdout
    assert "backtest-swing" in result.stdout
    assert "backtest-intraday" in result.stdout
    assert "Swing trading workflow" not in result.stdout
    assert "Intraday screening" not in result.stdout
    assert "Opening session learning" not in result.stdout


def test_removed_legacy_trade_groups_are_not_callable():
    for group in ("swing", "intraday", "opening"):
        result = runner.invoke(app, ["trade", group, "--help"])

        assert result.exit_code != 0


def test_trade_log_group_keeps_journals_distinct():
    result = runner.invoke(app, ["trade", "log", "--help"])

    assert result.exit_code == 0
    assert "intraday" in result.stdout
    assert "swing" in result.stdout


def test_trade_review_group_keeps_journals_distinct():
    result = runner.invoke(app, ["trade", "review", "--help"])

    assert result.exit_code == 0
    assert "intraday" in result.stdout
    assert "swing" in result.stdout


def test_strategy_group_exposes_skill_commands():
    result = runner.invoke(app, ["strategy", "--help"])

    assert result.exit_code == 0
    assert "skill" in result.stdout


def test_strategy_skill_group_executes_help():
    result = runner.invoke(app, ["strategy", "skill", "--help"])

    assert result.exit_code == 0
    assert "generate" in result.stdout
    assert "check" in result.stdout
    assert "index" in result.stdout


def test_removed_root_skill_group_is_not_callable():
    result = runner.invoke(app, ["skill", "--help"])

    assert result.exit_code != 0
