"""CLI option/removal/contract tests for swing commands."""

import inspect

from src.adapters.cli import plan_swing_commands as swing_cli
from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


def test_swing_command_defaults_do_not_apply_setup_and_include_regime():
    params = inspect.signature(swing_cli.swing).parameters

    assert params["setup"].default is None
    assert params["with_market_context"].default is False
    assert params["strategy"].default is None
    assert "profile" not in params


def test_swing_profile_flag_is_removed():
    result = runner.invoke(app, ["plan", "swing", "BBCA", "--profile", "balanced"])
    assert result.exit_code != 0


def test_old_regime_flags_fail_as_unknown_options():
    result_with = runner.invoke(app, ["plan", "swing", "BBCA", "--with-regime"])
    assert result_with.exit_code != 0

    result_no = runner.invoke(app, ["plan", "swing", "BBCA", "--no-regime"])
    assert result_no.exit_code != 0


def test_swing_deprecated_no_backtest_flag_is_removed():
    result = runner.invoke(app, ["plan", "swing", "BBCA", "--no-backtest"])

    assert result.exit_code != 0


def test_swing_deprecated_no_sentiment_flag_is_removed():
    result = runner.invoke(app, ["plan", "swing", "BBCA", "--no-sentiment"])

    assert result.exit_code != 0


def test_swing_backtest_has_no_tuning_diff_apply_flag():
    from src.adapters.cli import policy_accum_backtest_commands

    params = inspect.signature(
        policy_accum_backtest_commands.swing_backtest
    ).parameters
    result = runner.invoke(
        app,
        [
            "policy",
            "accum",
            "backtest",
            "BBCA",
            "--apply-tuning-diff",
        ],
    )

    assert "apply_tuning_diff" not in params
    assert result.exit_code != 0
    assert "apply-tuning-diff" in result.output


def test_swing_compare_route_retired():
    """ADR-050: swing-compare removed; no unknown-variant path remains."""
    from src.adapters.cli.main import app
    from typer.testing import CliRunner
    result = CliRunner().invoke(app, ["analyze", "swing-compare", "--help"])
    assert result.exit_code != 0

