"""Tests for IDX tick size domain value object."""

from decimal import Decimal

import pytest

from src.domain.value_objects import tick_size as ts


class TestForPrice:
    def test_below_200(self):
        assert ts.for_price(Decimal("50")) == 1
        assert ts.for_price(Decimal("199")) == 1

    def test_200_to_499(self):
        assert ts.for_price(Decimal("200")) == 2
        assert ts.for_price(Decimal("499")) == 2

    def test_500_to_1999(self):
        assert ts.for_price(Decimal("500")) == 5
        assert ts.for_price(Decimal("1999")) == 5

    def test_2000_to_4999(self):
        assert ts.for_price(Decimal("2000")) == 10
        assert ts.for_price(Decimal("4999")) == 10

    def test_5000_and_above(self):
        assert ts.for_price(Decimal("5000")) == 25
        assert ts.for_price(Decimal("10000")) == 25

    def test_raises_on_zero(self):
        with pytest.raises(ValueError):
            ts.for_price(Decimal("0"))

    def test_raises_on_negative(self):
        with pytest.raises(ValueError):
            ts.for_price(Decimal("-100"))


class TestTicksBetween:
    def test_basic(self):
        # Price 5000 → tick 25; 5075 - 5000 = 75 / 25 = 3 ticks
        assert ts.ticks_between(Decimal("5000"), Decimal("5075")) == 3

    def test_fractional_rounds_down(self):
        # 5000 → tick 25; 5060 - 5000 = 60 / 25 = 2 ticks (floor)
        assert ts.ticks_between(Decimal("5000"), Decimal("5060")) == 2

    def test_low_price_tier(self):
        # Price 100 → tick 1; 103 - 100 = 3 ticks
        assert ts.ticks_between(Decimal("100"), Decimal("103")) == 3

    def test_upper_lte_lower_returns_zero(self):
        assert ts.ticks_between(Decimal("5000"), Decimal("5000")) == 0
        assert ts.ticks_between(Decimal("5000"), Decimal("4900")) == 0


class TestTickFrictionGateIntegration:
    """Test tick-friction gate inside ConfirmIntradayOpenUseCase."""

    def _make_candidate(self, opening, atr_stop):
        from decimal import Decimal

        from src.domain.value_objects.intraday_confirmation import IntradayConfirmationCandidate
        return IntradayConfirmationCandidate(
            ticker="BBCA",
            opening_price=Decimal(str(opening)),
            entry_range_low=Decimal(str(opening - 100)),
            entry_range_high=Decimal(str(opening + 100)),
            suggested_entry=Decimal(str(opening)),
            atr_stop=Decimal(str(atr_stop)),
            trend="BULLISH",
            accum_tag="BACKED",
        )

    def _run(self, opening, atr_stop, tick_friction_gate=True, min_target_ticks=3, min_stop_ticks=2):
        from src.application.use_case.confirm_intraday_open_use_case import (
            ConfirmIntradayOpenRequest,
            ConfirmIntradayOpenUseCase,
        )
        uc = ConfirmIntradayOpenUseCase()
        request = ConfirmIntradayOpenRequest(
            candidates=[self._make_candidate(opening, atr_stop)],
            tick_friction_gate=tick_friction_gate,
            min_target_ticks=min_target_ticks,
            min_stop_ticks=min_stop_ticks,
        )
        return uc.execute(request).confirmations[0]

    def test_sufficient_ticks_enters(self):
        # Entry=5000, stop=4925 → 3 ticks stop, 3 ticks target (25×3=75) → ENTER
        result = self._run(5000, 4925)
        from src.domain.value_objects.intraday_confirmation import IntradayDecision
        assert result.decision == IntradayDecision.ENTER

    def test_insufficient_ticks_skips(self):
        # Entry=5000, stop=4990 → only 0.4 ticks stop/target → SKIP_LOW_VOLATILITY
        result = self._run(5000, 4990)
        from src.domain.value_objects.intraday_confirmation import IntradayDecision
        assert result.decision == IntradayDecision.SKIP_LOW_VOLATILITY
        assert "tick-friction" in result.reasons[-1]

    def test_gate_disabled_bypasses_check(self):
        # Same tight setup but gate disabled → ENTER
        result = self._run(5000, 4990, tick_friction_gate=False)
        from src.domain.value_objects.intraday_confirmation import IntradayDecision
        assert result.decision == IntradayDecision.ENTER
