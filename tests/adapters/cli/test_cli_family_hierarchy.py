"""CLI family grammar: trade paper, research corpus, policy config lifecycle."""

from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_contextual_routes_are_exposed() -> None:
    research = runner.invoke(app, ["research", "--help"])
    accum = runner.invoke(app, ["research", "accum", "--help"])
    pre_open = runner.invoke(app, ["research", "pre-open", "--help"])
    policy = runner.invoke(app, ["policy", "accum", "--help"])
    trade = runner.invoke(app, ["trade", "--help"])
    trade_pre = runner.invoke(app, ["trade", "pre-open", "--help"])
    trade_accum = runner.invoke(app, ["trade", "accum", "--help"])

    assert research.exit_code == 0
    assert "signal" not in research.stdout
    assert "accumulation" not in research.stdout
    assert "accum" in research.stdout
    assert all(
        command in accum.stdout
        for command in ("capture", "backfill", "labels", "evaluate", "replay", "status")
    )
    assert all(
        command in pre_open.stdout
        for command in ("capture", "track", "labels", "evaluate", "status")
    )
    assert all(
        command in policy.stdout
        for command in ("backtest", "tune", "review", "validate", "apply", "status")
    )
    assert trade.exit_code == 0
    assert "pre-open" in trade.stdout
    assert "accum" in trade.stdout
    assert all(cmd in trade_pre.stdout for cmd in ("log", "outcome", "review"))
    assert all(cmd in trade_accum.stdout for cmd in ("log", "review"))
    assert "outcome" not in trade_accum.stdout or "outcome" in trade_pre.stdout


def test_removed_routes_fail() -> None:
    removed = (
        ["research", "signal", "--help"],
        ["research", "accumulation", "--help"],
        ["research", "pre-open", "grade", "--help"],
        ["research", "pre-open", "prompt", "--help"],
        ["research", "pre-open", "tune", "--help"],
        ["trade", "log", "--help"],
        ["trade", "outcome", "--help"],
        ["trade", "review", "--help"],
        ["trade", "size", "--help"],
        ["trade", "swing", "--help"],
        ["trade", "backtest-intraday", "--help"],
        ["trade", "migrate-journal", "--help"],
        ["trade", "backtest-swing", "--help"],
        ["trade", "tune-swing", "--help"],
        ["trade", "review-tuning-swing", "--help"],
        ["trade", "validate-tuning-patch", "--help"],
        ["trade", "apply-tuning-patch", "--help"],
        ["trade", "tuning-status", "--help"],
        ["trade", "review", "pre-open", "--help"],
        ["trade", "review", "swing", "--help"],
        ["trade", "log", "--type", "pre-open"],
        ["trade", "log", "--type", "swing"],
    )

    for args in removed:
        assert runner.invoke(app, args).exit_code != 0, args


def test_removed_learning_flags_are_absent() -> None:
    pre_open_labels = runner.invoke(
        app, ["research", "pre-open", "labels", "--help"]
    )
    policy_tune = runner.invoke(app, ["policy", "accum", "tune", "--help"])

    assert "--no-persist" not in pre_open_labels.stdout
    assert "--export-patch" not in policy_tune.stdout
    assert "--journal" not in policy_tune.stdout


def test_plan_family_exposes_swing_and_retires_analyze_swing() -> None:
    plan = runner.invoke(app, ["plan", "--help"])
    assert plan.exit_code == 0
    assert "swing" in plan.stdout
    assert runner.invoke(app, ["plan", "swing", "--help"]).exit_code == 0
    assert runner.invoke(app, ["analyze", "swing", "--help"]).exit_code != 0
    assert runner.invoke(app, ["analyze", "swing-compare", "--help"]).exit_code != 0
    assert runner.invoke(app, ["analyze", "compare", "--help"]).exit_code != 0
