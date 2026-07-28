"""Tests for the shared ATR/volatility classification helper.

This is the single source of truth used by both plan swing's diagnostic
volatility panel and the persisted SignalObservationFingerprint volatility
fields. Both call sites must agree on bucket/multiplier logic.
"""

from decimal import Decimal

from src.application.services.volatility_context import (
    VolatilityContext,
    build_volatility_context,
)


def test_build_volatility_context_normal_bucket_with_decimal_inputs():
    vc = build_volatility_context(atr_value=Decimal("3"), latest_close=Decimal("100"))

    assert vc.atr_at_signal == 3.0
    assert vc.atr_pct_at_signal == 3.0
    assert vc.volatility_bucket_at_signal == "NORMAL"
    assert vc.volatility_size_multiplier_at_signal == 1.0


def test_build_volatility_context_atr_none_yields_unknown():
    vc = build_volatility_context(atr_value=None, latest_close=Decimal("100"))

    assert vc.atr_at_signal is None
    assert vc.atr_pct_at_signal is None
    assert vc.volatility_bucket_at_signal == "UNKNOWN"
    assert vc.volatility_size_multiplier_at_signal == 1.0


def test_build_volatility_context_latest_close_none_yields_unknown():
    vc = build_volatility_context(atr_value=Decimal("3"), latest_close=None)

    assert vc.atr_pct_at_signal is None
    assert vc.volatility_bucket_at_signal == "UNKNOWN"
    # atr itself is still captured even though pct cannot be computed.
    assert vc.atr_at_signal == 3.0


def test_build_volatility_context_zero_close_is_division_guarded():
    vc = build_volatility_context(atr_value=Decimal("3"), latest_close=Decimal("0"))

    assert vc.atr_pct_at_signal is None
    assert vc.volatility_bucket_at_signal == "UNKNOWN"


def test_build_volatility_context_boundary_two_pct_is_normal_not_low():
    # atr_pct == 2.0 exactly -> condition is `< 2.0`, so NOT LOW.
    vc = build_volatility_context(atr_value=Decimal("2"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 2.0
    assert vc.volatility_bucket_at_signal == "NORMAL"
    assert vc.volatility_size_multiplier_at_signal == 1.0


def test_build_volatility_context_boundary_five_pct_is_high():
    # atr_pct == 5.0 exactly -> condition is `< 5.0`, so NOT NORMAL.
    vc = build_volatility_context(atr_value=Decimal("5"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 5.0
    assert vc.volatility_bucket_at_signal == "HIGH"
    assert vc.volatility_size_multiplier_at_signal == 0.75


def test_build_volatility_context_boundary_eight_pct_is_extreme():
    # atr_pct == 8.0 exactly -> condition is `< 8.0`, so NOT HIGH.
    vc = build_volatility_context(atr_value=Decimal("8"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 8.0
    assert vc.volatility_bucket_at_signal == "EXTREME"
    assert vc.volatility_size_multiplier_at_signal == 0.50


def test_build_volatility_context_low_bucket_below_two_pct():
    vc = build_volatility_context(atr_value=Decimal("1"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 1.0
    assert vc.volatility_bucket_at_signal == "LOW"
    assert vc.volatility_size_multiplier_at_signal == 1.0


def test_build_volatility_context_high_bucket_multiplier_is_075():
    vc = build_volatility_context(atr_value=Decimal("6"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 6.0
    assert vc.volatility_bucket_at_signal == "HIGH"
    assert vc.volatility_size_multiplier_at_signal == 0.75


def test_build_volatility_context_extreme_bucket_multiplier_is_050():
    vc = build_volatility_context(atr_value=Decimal("10"), latest_close=Decimal("100"))

    assert vc.atr_pct_at_signal == 10.0
    assert vc.volatility_bucket_at_signal == "EXTREME"
    assert vc.volatility_size_multiplier_at_signal == 0.50


def test_build_volatility_context_accepts_plain_floats():
    vc = build_volatility_context(atr_value=6.0, latest_close=100.0)

    assert isinstance(vc, VolatilityContext)
    assert vc.atr_at_signal == 6.0
    assert vc.atr_pct_at_signal == 6.0
    assert vc.volatility_bucket_at_signal == "HIGH"
    assert vc.volatility_size_multiplier_at_signal == 0.75
