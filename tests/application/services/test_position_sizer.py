"""Unit tests for position_sizer service."""

from decimal import Decimal

import pytest

from src.application.services.position_sizer import (
    SHARES_PER_LOT,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)


def _size(
    entry="5000",
    atr="150",
    capital="10000000",
    risk_pct="0.01",
    atr_multiplier="1.5",
    reward_risk="2.0",
) -> SizingResult:
    return compute_position_size(
        entry=Decimal(entry),
        atr=Decimal(atr),
        capital=Decimal(capital),
        risk_pct=Decimal(risk_pct),
        atr_multiplier=Decimal(atr_multiplier),
        reward_risk=Decimal(reward_risk),
    )


class TestComputePositionSize:
    def test_basic_calculation(self):
        r = _size(entry="5000", atr="150", capital="10000000", risk_pct="0.01")

        assert r.entry_price == Decimal("5000")
        assert r.atr == Decimal("150")
        # stop_distance = 1.5 × 150 = 225
        assert r.stop_distance == Decimal("225")
        # stop_price = 5000 - 225 = 4775
        assert r.stop_price == Decimal("4775")
        # target_price = 5000 + 2 × 225 = 5450
        assert r.target_price == Decimal("5450")

    def test_stop_pct_is_negative(self):
        r = _size(entry="5000", atr="150")
        assert r.stop_pct < 0

    def test_target_pct_is_positive(self):
        r = _size(entry="5000", atr="150")
        assert r.target_pct > 0

    def test_reward_risk_symmetry(self):
        r = _size(entry="5000", atr="150", reward_risk="2.0")
        # reward = 2 × risk per lot
        assert abs(r.target_pct) == pytest.approx(abs(float(r.stop_pct)) * 2, rel=0.01)

    def test_lot_rounding_to_100(self):
        r = _size()
        assert r.shares % SHARES_PER_LOT == 0
        assert r.lots == r.shares // SHARES_PER_LOT

    def test_risk_amount_equals_capital_times_risk_pct(self):
        r = _size(capital="10000000", risk_pct="0.01")
        assert r.risk_amount == Decimal("100000")

    def test_position_cost_is_shares_times_entry(self):
        r = _size()
        assert r.position_cost == Decimal(str(r.shares)) * r.entry_price

    def test_capital_used_pct_range(self):
        r = _size()
        assert 0 <= float(r.capital_used_pct) <= 100

    def test_lots_is_zero_when_capital_too_small(self):
        # Very small capital — cannot afford 100 shares
        r = _size(entry="50000", atr="5000", capital="1000", risk_pct="0.01")
        assert r.lots == 0
        assert r.shares == 0
        assert r.position_cost == Decimal("0")

    def test_raises_on_zero_atr(self):
        with pytest.raises(ValueError, match="ATR must be positive"):
            compute_position_size(
                entry=Decimal("5000"),
                atr=Decimal("0"),
                capital=Decimal("10000000"),
                risk_pct=Decimal("0.01"),
            )

    def test_raises_on_negative_atr(self):
        with pytest.raises(ValueError, match="ATR must be positive"):
            compute_position_size(
                entry=Decimal("5000"),
                atr=Decimal("-50"),
                capital=Decimal("10000000"),
                risk_pct=Decimal("0.01"),
            )

    def test_custom_atr_multiplier(self):
        r = _size(atr="100", atr_multiplier="2.0")
        assert r.stop_distance == Decimal("200")
        assert r.atr_multiplier == Decimal("2.0")

    def test_custom_reward_risk(self):
        r = _size(atr="100", reward_risk="3.0")
        assert r.reward_risk_ratio == Decimal("3.0")
        assert r.reward_amount == pytest.approx(r.risk_amount * 3, rel=0.01)

    def test_result_is_frozen(self):
        r = _size()
        with pytest.raises(Exception):
            r.lots = 99  # type: ignore

    def test_high_capital_larger_position(self):
        small = _size(capital="10000000")
        large = _size(capital="100000000")
        assert large.lots > small.lots

    def test_atr_based_stop_not_affected_by_capital(self):
        small = _size(capital="10000000")
        large = _size(capital="100000000")
        # Stop price is entry - mult*ATR, independent of capital
        assert small.stop_price == large.stop_price
        assert small.stop_distance == large.stop_distance


class TestComputePercentPositionSize:
    def test_basic_percent_sizing(self):
        result = compute_percent_position_size(
            entry=Decimal("1000"),
            capital=Decimal("10000000"),
            risk_pct=Decimal("0.01"),
            stop_loss_pct=Decimal("5"),
            take_profit_pct=Decimal("5"),
        )

        assert result.stop_price == Decimal("950")
        assert result.target_price == Decimal("1050")
        assert result.stop_distance == Decimal("50")
        assert result.risk_amount == Decimal("100000.00")
        assert result.lots == 20
        assert result.shares == 2000

    def test_percent_sizing_rounds_to_lots(self):
        result = compute_percent_position_size(
            entry=Decimal("700"),
            capital=Decimal("10000000"),
            risk_pct=Decimal("0.01"),
            stop_loss_pct=Decimal("5"),
            take_profit_pct=Decimal("5"),
        )

        assert result.shares % SHARES_PER_LOT == 0
        assert result.lots == result.shares // SHARES_PER_LOT

    def test_percent_sizing_rejects_invalid_stop(self):
        with pytest.raises(ValueError, match="Stop loss percent must be positive"):
            compute_percent_position_size(
                entry=Decimal("1000"),
                capital=Decimal("10000000"),
                risk_pct=Decimal("0.01"),
                stop_loss_pct=Decimal("0"),
                take_profit_pct=Decimal("5"),
            )
