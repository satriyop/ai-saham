"""Tests for evaluate_foreign_bounce_gates and compute_percent_plan."""

from decimal import Decimal

import pytest

from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    compute_percent_plan,
    evaluate_foreign_bounce_gates,
)

# ── helpers ────────────────────────────────────────────────────────────────────

def _candidate(**kwargs) -> AccumulationCandidate:
    from decimal import Decimal
    defaults = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("9000"),
        current_price=Decimal("8640"),
        vwap_discount_pct=4.0,
        rsi=45.0,
        trend="SIDE",
        accum_score=80.0,
        top_brokers=["AK", "BK"],
        institutional_flag=True,
        avg_flow_ratio=6.0,
    )
    defaults.update(kwargs)
    return AccumulationCandidate(**defaults)


_GATE_DEFAULTS = dict(
    gate_min_score=70.0,
    gate_min_vwap_discount_pct=3.0,
    gate_required_trend="SIDE",
    gate_min_flow_ratio_pct=5.0,
    gate_max_rsi=60.0,
    watch_max_failed_gates=2,
)


def _eval(candidate, **overrides):
    params = {**_GATE_DEFAULTS, **overrides}
    return evaluate_foreign_bounce_gates(candidate, **params)


# ── evaluate_foreign_bounce_gates ──────────────────────────────────────────────

def test_all_gates_pass_returns_enter():
    c = _candidate()
    classification, failed = _eval(c)
    assert classification == "ENTER"
    assert failed == ()


def test_single_gate_fail_returns_watch():
    c = _candidate(rsi=65.0)
    classification, failed = _eval(c)
    assert classification == "WATCH"
    assert any("RSI" in f for f in failed)


def test_many_gates_fail_returns_avoid():
    c = _candidate(rsi=75.0, trend="UP", avg_flow_ratio=1.0, vwap_discount_pct=0.5, accum_score=30.0)
    classification, failed = _eval(c)
    assert classification == "AVOID"
    assert len(failed) > 2


def test_score_gate_fail_but_few_total_fails_returns_watch():
    # Score fails, but only 1 other gate fails (≤ watch_max_failed_gates=2)
    c = _candidate(accum_score=60.0, rsi=65.0)  # 2 failures: score + RSI
    classification, failed = _eval(c)
    assert classification == "WATCH"


def test_failed_gates_contain_required_values():
    c = _candidate(rsi=75.0)
    _, failed = _eval(c)
    assert any("<= 60" in f for f in failed)


def test_none_rsi_fails_rsi_present_gate():
    c = _candidate(rsi=None)
    _, failed = _eval(c)
    assert any("RSI present" in f for f in failed)


def test_none_vwap_fails_vwap_gate():
    c = _candidate(vwap_discount_pct=None)
    _, failed = _eval(c)
    assert any("vwap_disc_pct" in f for f in failed)


def test_wrong_trend_fails_trend_gate():
    c = _candidate(trend="UP")
    _, failed = _eval(c)
    assert any("trend" in f for f in failed)


def test_custom_gate_values_respected():
    c = _candidate(accum_score=50.0)
    # With min_score=40.0, score gate should pass
    classification, failed = _eval(c, gate_min_score=40.0)
    assert not any("score" in f for f in failed)


# ── compute_percent_plan ───────────────────────────────────────────────────────

def test_percent_plan_basic():
    stop, target = compute_percent_plan(
        Decimal("1000"), stop_pct=Decimal("5"), target_pct=Decimal("5")
    )
    assert stop == pytest.approx(Decimal("950"))
    assert target == pytest.approx(Decimal("1050"))


def test_percent_plan_asymmetric():
    stop, target = compute_percent_plan(
        Decimal("2000"), stop_pct=Decimal("4"), target_pct=Decimal("8")
    )
    assert stop == pytest.approx(Decimal("1920"))
    assert target == pytest.approx(Decimal("2160"))
