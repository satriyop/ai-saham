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


def test_assess_family_exposes_pre_open_and_retires_analyze_pre_open() -> None:
    assess = runner.invoke(app, ["assess", "--help"])
    assert assess.exit_code == 0
    assert "pre-open" in assess.stdout
    assert runner.invoke(app, ["assess", "pre-open", "--help"]).exit_code == 0
    assert runner.invoke(app, ["analyze", "pre-open", "--help"]).exit_code != 0


def test_inspect_family_and_analyze_retired() -> None:
    inspect = runner.invoke(app, ["inspect", "--help"])
    assert inspect.exit_code == 0
    for cmd in ("risk", "sentiment", "regime", "signal"):
        assert cmd in inspect.stdout
    assert "chart" not in inspect.stdout
    assert runner.invoke(app, ["inspect", "risk", "--help"]).exit_code == 0
    assert runner.invoke(app, ["inspect", "signal", "--help"]).exit_code == 0
    assert "accum" in runner.invoke(app, ["inspect", "signal", "--help"]).stdout
    assert runner.invoke(app, ["inspect", "signal", "accum", "--help"]).exit_code == 0
    # Bare inspect signal TICKER is retired (purpose required).
    bare = runner.invoke(app, ["inspect", "signal", "BBCA"])
    assert bare.exit_code != 0
    assert runner.invoke(app, ["audit", "sentiment", "--help"]).exit_code == 0
    assert runner.invoke(app, ["analyze", "--help"]).exit_code != 0
    for retired in (
        ["analyze", "risk", "--help"],
        ["analyze", "sentiment", "--help"],
        ["analyze", "audit", "--help"],
        ["analyze", "signal", "inspect", "--help"],
    ):
        assert runner.invoke(app, retired).exit_code != 0, retired


def test_inspect_signal_accum_help_names_accumulation_flow() -> None:
    result = runner.invoke(app, ["inspect", "signal", "accum", "--help"])
    assert result.exit_code == 0
    lower = result.stdout.lower()
    assert "accumulation-flow" in lower or "accumulation flow" in lower or "accum" in lower
    assert "pre-open" in lower or "not pre-open" in lower or "plan swing" in lower


def test_inspect_chart_retired() -> None:
    assert runner.invoke(app, ["inspect", "chart", "--help"]).exit_code != 0
    assert runner.invoke(app, ["inspect", "chart", "price", "--help"]).exit_code != 0


def test_view_market_context_retired_use_inspect_regime() -> None:
    # Command unmounted from view (bare token may still hit ticker-show router).
    view_help = runner.invoke(app, ["view", "--help"])
    assert view_help.exit_code == 0
    assert "market-context" not in view_help.stdout
    assert runner.invoke(app, ["inspect", "regime", "--help"]).exit_code == 0
