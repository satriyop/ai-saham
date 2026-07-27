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
    assert "evaluate" in result.stdout
    assert "status" in result.stdout
    assert "grade" not in result.stdout
    assert "prompt" not in result.stdout
    assert "tune" not in result.stdout


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


def test_plan_swing_is_available():
    result = runner.invoke(app, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "swing" in result.stdout


def test_deprecated_save_session_path_is_removed():
    result = runner.invoke(app, ["trade", "intraday", "--help"])

    assert result.exit_code != 0


def test_trade_group_exposes_paper_notebook_only():
    result = runner.invoke(app, ["trade", "--help"])

    assert result.exit_code == 0
    assert "confirm" not in result.stdout  # post-open assess → analyze pre-open
    assert "pre-open" in result.stdout
    assert "accum" in result.stdout
    # Commands section must not expose retired flat verbs / groups
    assert "backtest-intraday" not in result.stdout
    for retired in ("size", "migrate-journal"):
        # may appear only as cross-links in help prose; require Commands block absence
        assert f"│ {retired}" not in result.stdout and f"  {retired} " not in result.stdout
    # no trade swing subgroup
    assert "trade swing" not in result.stdout
    assert "│ swing" not in result.stdout
    assert "Swing trading workflow" not in result.stdout
    assert "Intraday screening" not in result.stdout
    assert "Opening session learning" not in result.stdout


def test_removed_legacy_trade_groups_are_not_callable():
    for group in ("intraday", "opening", "confirm", "log", "review", "outcome", "swing", "size"):
        result = runner.invoke(app, ["trade", group, "--help"])

        assert result.exit_code != 0


def test_trade_pre_open_and_accum_journals_are_distinct():
    pre = runner.invoke(app, ["trade", "pre-open", "--help"])
    accum = runner.invoke(app, ["trade", "accum", "--help"])

    assert pre.exit_code == 0
    assert accum.exit_code == 0
    assert "log" in pre.stdout
    assert "outcome" in pre.stdout
    assert "review" in pre.stdout
    assert "log" in accum.stdout
    assert "review" in accum.stdout


def test_policy_group_exposes_accum_lifecycle():
    result = runner.invoke(app, ["policy", "--help"])
    accum = runner.invoke(app, ["policy", "accum", "--help"])

    assert result.exit_code == 0
    assert "accum" in result.stdout
    assert accum.exit_code == 0
    for verb in ("backtest", "tune", "review", "validate", "apply", "status"):
        assert verb in accum.stdout


def test_analyze_group_exposes_pre_open_post_open_assess():
    result = runner.invoke(app, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "pre-open" in result.stdout


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
