from decimal import Decimal

from src.application.services.stats import (
    average,
    foreign_vwap_discount_pct,
    interpolate,
    max_drawdown_pct,
    pct_change,
    profit_factor,
    win_rate,
)


def test_average_skips_none_and_applies_precision():
    assert average([1.0, None, 2.0], precision=2) == 1.5
    assert average([None], precision=2) is None


def test_pct_change_guards_zero_base():
    assert pct_change(Decimal("110"), Decimal("100")) == 10.0
    assert pct_change(Decimal("110"), Decimal("0")) == 0.0


def test_interpolate_handles_flat_range():
    assert interpolate(12.5, 10.0, 15.0, 95.0, 75.0) == 85.0
    assert interpolate(12.5, 10.0, 10.0, 95.0, 75.0) == 75.0


def test_foreign_vwap_discount_pct_preserves_requested_precision():
    assert foreign_vwap_discount_pct(Decimal("105"), Decimal("100")) == 5.0
    assert foreign_vwap_discount_pct(Decimal("105.555"), Decimal("100"), precision=2) == 5.55
    assert foreign_vwap_discount_pct(Decimal("105"), Decimal("0")) is None


def test_win_rate_skips_none_and_uses_strict_positive():
    assert win_rate([1.0, 0.0, -1.0, None], precision=2) == 33.33
    assert win_rate([None], precision=2) is None


def test_profit_factor_handles_zero_loss_cases():
    assert profit_factor([Decimal("10"), Decimal("-5")], precision=4) == 2.0
    assert profit_factor([Decimal("10")]) == float("inf")
    assert profit_factor([]) is None


def test_max_drawdown_pct_tracks_peak_to_trough():
    assert max_drawdown_pct([Decimal("100"), Decimal("120"), Decimal("90")]) == -25.0
    assert max_drawdown_pct([]) == 0.0
