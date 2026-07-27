"""CLI option/removal/contract tests for swing commands."""

import inspect

from src.adapters.cli import analyze_swing_commands as swing_cli
from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


def test_swing_command_defaults_do_not_apply_setup_and_include_regime():
    params = inspect.signature(swing_cli.swing).parameters

    assert params["setup"].default is None
    assert params["with_market_context"].default is False
    assert params["strategy"].default is None
    assert "profile" not in params


def test_swing_profile_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--profile", "balanced"])
    assert result.exit_code != 0


def test_old_regime_flags_fail_as_unknown_options():
    result_with = runner.invoke(app, ["analyze", "swing", "BBCA", "--with-regime"])
    assert result_with.exit_code != 0

    result_no = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-regime"])
    assert result_no.exit_code != 0


def test_swing_deprecated_no_backtest_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-backtest"])

    assert result.exit_code != 0


def test_swing_deprecated_no_sentiment_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-sentiment"])

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


def test_swing_compare_rejects_unknown_variant():
    result = runner.invoke(
        app,
        [
            "analyze",
            "swing-compare",
            "BBCA",
            "--variants",
            "baseline,unknown",
        ],
    )

    assert result.exit_code != 0
    assert "unknown" in result.output.lower()
