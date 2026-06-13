"""Tests for swing command helper logic."""

from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.swing_commands import (
    FOREIGN_BOUNCE_PRESET,
    _evaluate_foreign_bounce,
)
from src.application.use_case.accumulation_screen import AccumulationCandidate

runner = CliRunner()


def _candidate(**overrides) -> AccumulationCandidate:
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def test_foreign_bounce_passes_all_gates():
    evaluation = _evaluate_foreign_bounce(_candidate())

    assert evaluation.name == FOREIGN_BOUNCE_PRESET
    assert evaluation.passed is True
    assert evaluation.classification == "ENTER"
    assert evaluation.failed_reasons == ()


def test_foreign_bounce_reports_failed_gates():
    evaluation = _evaluate_foreign_bounce(
        _candidate(score=70.0, trend="DOWN")
    )

    assert evaluation.passed is False
    assert evaluation.classification == "WATCH"
    assert any("trend" in reason for reason in evaluation.failed_reasons)


def test_foreign_bounce_missing_accumulation_is_avoid():
    evaluation = _evaluate_foreign_bounce(None)

    assert evaluation.passed is False
    assert evaluation.classification == "AVOID"


def test_swing_backtest_unknown_preset_error():
    result = runner.invoke(app, ["swing", "backtest", "--preset", "unknown"])

    assert result.exit_code != 0
    assert "unknown swing preset" in result.output.lower()
    assert FOREIGN_BOUNCE_PRESET in result.output


def test_regime_command_accepts_explicit_ticker_with_empty_cache(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "regime",
            "BBCA",
            "--universe",
            "cached",
            "--db",
            str(tmp_path / "empty.db"),
            "--as-of",
            "2026-06-12",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "MARKET REGIME" in result.output
    assert "RISK_OFF" in result.output


def test_swing_backtest_rejects_invalid_allowed_regime():
    result = runner.invoke(
        app,
        [
            "swing",
            "backtest",
            "BBCA",
            "--allow-regimes",
            "CALM",
        ],
    )

    assert result.exit_code != 0
    assert "--allow-regimes" in result.output


def test_swing_compare_rejects_unknown_variant():
    result = runner.invoke(
        app,
        [
            "swing",
            "compare",
            "BBCA",
            "--variants",
            "baseline,unknown",
        ],
    )

    assert result.exit_code != 0
    assert "unknown" in result.output.lower()
    assert "baseline" in result.output
