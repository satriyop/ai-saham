"""Tests for swing command helper logic."""

from decimal import Decimal

from src.adapters.cli.swing_commands import (
    FOREIGN_BOUNCE_PRESET,
    _evaluate_foreign_bounce,
)
from src.application.use_case.accumulation_screen import AccumulationCandidate


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
