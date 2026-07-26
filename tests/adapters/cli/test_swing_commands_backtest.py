"""Backtest command validation tests for swing commands."""

from src.adapters.cli.analyze_swing_commands import FOREIGN_BOUNCE_SETUP_NAME
from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


def test_swing_backtest_unknown_setup_error():
    result = runner.invoke(app, ["trade", "swing", "backtest", "--setup", "unknown"])

    assert result.exit_code != 0
    assert "unknown swing setup" in result.output.lower()
    assert FOREIGN_BOUNCE_SETUP_NAME in result.output


def test_swing_backtest_rejects_invalid_allowed_regime():
    result = runner.invoke(
        app,
        [
            "trade",
            "swing",
            "backtest",
            "BBCA",
            "--allow-regimes",
            "CALM",
        ],
    )

    assert result.exit_code != 0
    assert "--allow-regimes" in result.output
