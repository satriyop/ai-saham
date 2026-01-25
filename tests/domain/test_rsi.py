"""
Tests for RSI indicator.

These tests verify:
- RSI calculation correctness (Wilder's smoothed moving average)
- SMA seeding for first average
- Edge cases (all gains, all losses, no change, insufficient data)
- Decimal precision
- RSI boundaries (always 0-100)
- Determinism

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle
from src.domain.indicators.rsi import calculate_rsi


# --- Test Fixtures ---


def make_candle(
    ticker: str,
    days_ago: int,
    close: str,
    open_price: str | None = None,
    high: str | None = None,
    low: str | None = None,
) -> Candle:
    """Create a test candle with specified prices."""
    close_dec = Decimal(close)
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=Decimal(open_price) if open_price else close_dec,
        high=Decimal(high) if high else close_dec,
        low=Decimal(low) if low else close_dec,
        close=close_dec,
        volume=100000,
    )


# --- Tests ---


class TestRSICalculation:
    """Test RSI calculation correctness."""

    def test_first_rsi_uses_sma_seed(self):
        """First RSI should use SMA for initial avg_gain and avg_loss."""
        # Create 4 candles: prices 100, 110, 105, 115
        # Deltas: +10, -5, +10
        # Gains: 10, 0, 10 -> avg_gain = 20/3
        # Losses: 0, 5, 0 -> avg_loss = 5/3
        # RS = (20/3) / (5/3) = 4
        # RSI = 100 - (100 / (1 + 4)) = 100 - 20 = 80
        candles = [
            make_candle("TEST", 3, "100.00"),
            make_candle("TEST", 2, "110.00"),
            make_candle("TEST", 1, "105.00"),
            make_candle("TEST", 0, "115.00"),
        ]

        result = calculate_rsi(candles, period=3)

        assert len(result) == 1
        expected_rsi = Decimal("80")
        assert result[0][1] == expected_rsi

    def test_rsi_with_known_dataset(self):
        """Verify RSI calculation with hand-calculated dataset."""
        # 5 candles: 100, 102, 101, 104, 103
        # Deltas: +2, -1, +3, -1
        # Gains: 2, 0, 3, 0
        # Losses: 0, 1, 0, 1

        # Period=3:
        # Initial (first 3 deltas): gains=[2,0,3], losses=[0,1,0]
        # avg_gain = 5/3, avg_loss = 1/3
        # RS = (5/3) / (1/3) = 5
        # RSI[0] = 100 - 100/(1+5) = 100 - 16.666... = 83.333...

        # Next (4th delta: -1, gain=0, loss=1):
        # avg_gain = ((5/3) * 2 + 0) / 3 = 10/9
        # avg_loss = ((1/3) * 2 + 1) / 3 = 5/9
        # RS = (10/9) / (5/9) = 2
        # RSI[1] = 100 - 100/(1+2) = 100 - 33.333... = 66.666...

        candles = [
            make_candle("TEST", 4, "100.00"),
            make_candle("TEST", 3, "102.00"),
            make_candle("TEST", 2, "101.00"),
            make_candle("TEST", 1, "104.00"),
            make_candle("TEST", 0, "103.00"),
        ]

        result = calculate_rsi(candles, period=3)

        assert len(result) == 2

        # First RSI: 100 - 100/6 = 83.333...
        # Use approximate comparison due to Decimal division rounding
        expected_rsi_0 = Decimal("83.3333")
        assert abs(result[0][1] - expected_rsi_0) < Decimal("0.001")

        # Second RSI: 100 - 100/3 = 66.666...
        expected_rsi_1 = Decimal("66.6667")
        assert abs(result[1][1] - expected_rsi_1) < Decimal("0.001")

    def test_rsi_uses_wilder_smoothing(self):
        """Verify Wilder's smoothing formula is applied correctly."""
        # Wilder's: avg(t) = (avg(t-1) * (period-1) + current) / period
        # This differs from standard EMA which uses k = 2/(period+1)

        candles = [
            make_candle("TEST", 4, "100.00"),
            make_candle("TEST", 3, "110.00"),  # +10
            make_candle("TEST", 2, "105.00"),  # -5
            make_candle("TEST", 1, "115.00"),  # +10
            make_candle("TEST", 0, "110.00"),  # -5
        ]

        result = calculate_rsi(candles, period=3)

        # Verify we have 2 RSI values
        assert len(result) == 2

        # First RSI at index 3 (candle index)
        # Deltas: +10, -5, +10
        # gains=[10,0,10], losses=[0,5,0]
        # avg_gain = 20/3, avg_loss = 5/3
        # RS = 4, RSI = 80
        assert result[0][1] == Decimal("80")

        # Second RSI (Wilder's smoothing)
        # 4th delta: -5, gain=0, loss=5
        # avg_gain = (20/3 * 2 + 0) / 3 = 40/9
        # avg_loss = (5/3 * 2 + 5) / 3 = 25/9
        # RS = (40/9) / (25/9) = 40/25 = 8/5 = 1.6
        # RSI = 100 - 100/(1 + 1.6) = 100 - 100/2.6 = 100 - 38.461... = 61.538...
        # Use approximate comparison due to Decimal division rounding
        expected_rsi = Decimal("61.5385")
        assert abs(result[1][1] - expected_rsi) < Decimal("0.001")

    def test_rsi_returns_date_and_value_tuples(self):
        """RSI should return tuples of (date, value)."""
        candles = [make_candle("TEST", i, f"{100 + i}.00") for i in range(10, -1, -1)]

        result = calculate_rsi(candles, period=5)

        for date_val, rsi_val in result:
            assert isinstance(date_val, date)
            assert isinstance(rsi_val, Decimal)

    def test_rsi_dates_match_candle_dates(self):
        """RSI dates should match the corresponding candle dates."""
        candles = [make_candle("TEST", i, f"{100 + i}.00") for i in range(5, -1, -1)]

        result = calculate_rsi(candles, period=3)

        # First RSI at candle index 3 (period), second at 4, third at 5
        assert len(result) == 3
        assert result[0][0] == candles[3].date
        assert result[1][0] == candles[4].date
        assert result[2][0] == candles[5].date


class TestRSIEdgeCases:
    """Test RSI edge cases."""

    def test_insufficient_data_returns_empty(self):
        """RSI with period >= candles should return empty list."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        # Need period + 1 candles minimum (5 candles for period=5)
        result = calculate_rsi(candles, period=5)
        assert result == []

        # 5 candles is exactly enough for period=4
        result = calculate_rsi(candles, period=4)
        assert len(result) == 1

    def test_empty_candles_returns_empty(self):
        """RSI with empty candles should return empty list."""
        result = calculate_rsi([], period=14)
        assert result == []

    def test_all_gains_rsi_equals_100(self):
        """RSI should be 100 when there are only gains (no losses)."""
        # Continuously increasing prices
        candles = [
            make_candle("TEST", 3, "100.00"),
            make_candle("TEST", 2, "110.00"),  # +10
            make_candle("TEST", 1, "120.00"),  # +10
            make_candle("TEST", 0, "130.00"),  # +10
        ]

        result = calculate_rsi(candles, period=3)

        assert len(result) == 1
        assert result[0][1] == Decimal("100")

    def test_all_losses_rsi_equals_0(self):
        """RSI should be 0 when there are only losses (no gains)."""
        # Continuously decreasing prices
        candles = [
            make_candle("TEST", 3, "130.00"),
            make_candle("TEST", 2, "120.00"),  # -10
            make_candle("TEST", 1, "110.00"),  # -10
            make_candle("TEST", 0, "100.00"),  # -10
        ]

        result = calculate_rsi(candles, period=3)

        assert len(result) == 1
        assert result[0][1] == Decimal("0")

    def test_no_change_rsi(self):
        """RSI with no price change should have avg_gain=0 and avg_loss=0."""
        # Constant prices
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_rsi(candles, period=3)

        # With avg_loss=0 (special case), RSI = 100
        # But avg_gain is also 0, so we check the _calculate_rsi_value logic
        # avg_loss=0 check comes first, so RSI = 100
        assert len(result) == 2
        assert result[0][1] == Decimal("100")

    def test_period_one_rsi(self):
        """RSI with period=1 should work correctly."""
        candles = [
            make_candle("TEST", 2, "100.00"),
            make_candle("TEST", 1, "110.00"),  # +10
            make_candle("TEST", 0, "105.00"),  # -5
        ]

        result = calculate_rsi(candles, period=1)

        # First RSI: gain=10, loss=0 -> RSI=100
        # Second RSI: Wilder's smoothing with period=1
        #   avg_gain = (10 * 0 + 0) / 1 = 0
        #   avg_loss = (0 * 0 + 5) / 1 = 5
        #   RSI = 0 (no gains)
        assert len(result) == 2
        assert result[0][1] == Decimal("100")
        assert result[1][1] == Decimal("0")

    def test_single_candle_above_minimum(self):
        """Minimum data for period=1 is 2 candles."""
        candles = [make_candle("TEST", 0, "100.00")]

        result = calculate_rsi(candles, period=1)
        assert result == []

        # 2 candles works for period=1
        candles = [
            make_candle("TEST", 1, "100.00"),
            make_candle("TEST", 0, "110.00"),
        ]
        result = calculate_rsi(candles, period=1)
        assert len(result) == 1


class TestRSIValidation:
    """Test RSI validation rules."""

    def test_period_zero_raises_error(self):
        """Period = 0 should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_rsi(candles, period=0)

    def test_negative_period_raises_error(self):
        """Negative period should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_rsi(candles, period=-5)


class TestRSIDecimalPrecision:
    """Test RSI maintains Decimal precision."""

    def test_decimal_precision_maintained(self):
        """RSI should maintain Decimal precision."""
        candles = [
            make_candle("TEST", 3, "100.123"),
            make_candle("TEST", 2, "100.456"),
            make_candle("TEST", 1, "100.234"),
            make_candle("TEST", 0, "100.789"),
        ]

        result = calculate_rsi(candles, period=3)

        assert len(result) == 1
        assert isinstance(result[0][1], Decimal)

    def test_no_floating_point_errors(self):
        """RSI should avoid floating point precision errors."""
        # Values that would cause floating point issues
        candles = [
            make_candle("TEST", 3, "0.1"),
            make_candle("TEST", 2, "0.2"),
            make_candle("TEST", 1, "0.15"),
            make_candle("TEST", 0, "0.25"),
        ]

        result = calculate_rsi(candles, period=3)

        # Should compute without floating point errors
        assert isinstance(result[0][1], Decimal)


class TestRSIDeterminism:
    """Test RSI produces deterministic results."""

    def test_same_input_same_output(self):
        """Same inputs should always produce same outputs."""
        candles = [make_candle("TEST", i, f"{100 + (i % 10)}.00") for i in range(20, -1, -1)]

        result1 = calculate_rsi(candles, period=14)
        result2 = calculate_rsi(candles, period=14)

        assert result1 == result2

    def test_different_periods_different_results(self):
        """Different periods should produce different results."""
        candles = [make_candle("TEST", i, f"{100 + (i % 10)}.00") for i in range(20, -1, -1)]

        result_7 = calculate_rsi(candles, period=7)
        result_14 = calculate_rsi(candles, period=14)

        assert result_7 != result_14
        assert len(result_7) > len(result_14)


class TestRSIBoundaries:
    """Test RSI boundaries (0-100 range)."""

    def test_rsi_always_between_0_and_100(self):
        """RSI values should always be between 0 and 100."""
        # Create a volatile price series
        prices = ["100", "120", "90", "130", "85", "140", "80", "150", "70", "160"]
        candles = [
            make_candle("TEST", len(prices) - 1 - i, price)
            for i, price in enumerate(prices)
        ]

        result = calculate_rsi(candles, period=3)

        for _, rsi_val in result:
            assert Decimal("0") <= rsi_val <= Decimal("100"), f"RSI {rsi_val} out of bounds"

    def test_extreme_price_moves_bounded(self):
        """RSI should be bounded even with extreme price movements."""
        # Extreme upward move
        candles = [
            make_candle("TEST", 3, "1.00"),
            make_candle("TEST", 2, "10.00"),    # +900%
            make_candle("TEST", 1, "100.00"),   # +900%
            make_candle("TEST", 0, "1000.00"),  # +900%
        ]

        result = calculate_rsi(candles, period=3)
        assert result[0][1] == Decimal("100")

        # Extreme downward move
        candles = [
            make_candle("TEST", 3, "1000.00"),
            make_candle("TEST", 2, "100.00"),   # -90%
            make_candle("TEST", 1, "10.00"),    # -90%
            make_candle("TEST", 0, "1.00"),     # -90%
        ]

        result = calculate_rsi(candles, period=3)
        assert result[0][1] == Decimal("0")

    def test_rsi_50_with_equal_gains_losses(self):
        """RSI should be 50 when average gains equal average losses."""
        # Price pattern: 100 -> 110 -> 100 -> 110 -> 100
        # Deltas: +10, -10, +10, -10
        candles = [
            make_candle("TEST", 4, "100.00"),
            make_candle("TEST", 3, "110.00"),
            make_candle("TEST", 2, "100.00"),
            make_candle("TEST", 1, "110.00"),
            make_candle("TEST", 0, "100.00"),
        ]

        result = calculate_rsi(candles, period=4)

        # gains=[10,0,10,0], losses=[0,10,0,10]
        # avg_gain = 20/4 = 5, avg_loss = 20/4 = 5
        # RS = 1, RSI = 100 - 100/2 = 50
        assert result[0][1] == Decimal("50")
