from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


def test_contextual_learning_routes_are_exposed() -> None:
    research = runner.invoke(app, ["research", "--help"])
    accumulation = runner.invoke(app, ["research", "accumulation", "--help"])
    pre_open = runner.invoke(app, ["research", "pre-open", "--help"])
    swing = runner.invoke(app, ["trade", "swing", "--help"])

    assert research.exit_code == 0
    assert "signal" not in research.stdout
    assert all(
        command in accumulation.stdout
        for command in ("capture", "backfill", "labels", "evaluate", "replay", "status")
    )
    assert all(
        command in pre_open.stdout
        for command in ("capture", "track", "labels", "evaluate", "status")
    )
    assert all(
        command in swing.stdout
        for command in ("backtest", "tune", "review", "validate", "apply", "status")
    )


def test_removed_routes_fail() -> None:
    removed = (
        ["research", "signal", "--help"],
        ["research", "pre-open", "grade", "--help"],
        ["research", "pre-open", "prompt", "--help"],
        ["research", "pre-open", "tune", "--help"],
        ["trade", "backtest-swing", "--help"],
        ["trade", "tune-swing", "--help"],
        ["trade", "review-tuning-swing", "--help"],
        ["trade", "validate-tuning-patch", "--help"],
        ["trade", "apply-tuning-patch", "--help"],
        ["trade", "tuning-status", "--help"],
    )

    for args in removed:
        assert runner.invoke(app, args).exit_code != 0, args


def test_removed_learning_flags_are_absent() -> None:
    pre_open_labels = runner.invoke(
        app, ["research", "pre-open", "labels", "--help"]
    )
    swing_tune = runner.invoke(app, ["trade", "swing", "tune", "--help"])

    assert "--no-persist" not in pre_open_labels.stdout
    assert "--export-patch" not in swing_tune.stdout
    assert "--journal" not in swing_tune.stdout
