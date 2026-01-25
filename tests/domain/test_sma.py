"""
Tests for SMA indicator.

These tests verify:
- SMA calculation correctness
- Edge cases (insufficient data, invalid inputs)
- Decimal precision
- Different price fields

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle
from src.domain.indicators.sma import calculate_sma


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


class TestSMACalculation:
    """Test SMA calculation correctness."""

    def test_simple_sma_calculation(self):
        """SMA should calculate correct average."""
        # Create 5 candles with prices [10, 20, 30, 40, 50] (oldest to newest)
        candles = [
            make_candle("TEST", 4, "10.00"),
            make_candle("TEST", 3, "20.00"),
            make_candle("TEST", 2, "30.00"),
            make_candle("TEST", 1, "40.00"),
            make_candle("TEST", 0, "50.00"),
        ]

        result = calculate_sma(candles, period=3)

        # Should get 3 SMA values:
        # SMA[2] = (10+20+30)/3 = 20
        # SMA[3] = (20+30+40)/3 = 30
        # SMA[4] = (30+40+50)/3 = 40
        assert len(result) == 3
        assert result[0][1] == Decimal("20")
        assert result[1][1] == Decimal("30")
        assert result[2][1] == Decimal("40")

    def test_sma_returns_date_and_value_tuples(self):
        """SMA should return tuples of (date, value)."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_sma(candles, period=3)

        assert len(result) == 3
        for date_val, sma_val in result:
            assert isinstance(date_val, date)
            assert isinstance(sma_val, Decimal)

    def test_sma_dates_match_candle_dates(self):
        """SMA dates should match the corresponding candle dates."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_sma(candles, period=3)

        # Result should align with candles starting at index 2 (period-1)
        assert result[0][0] == candles[2].date
        assert result[1][0] == candles[3].date
        assert result[2][0] == candles[4].date

    def test_sma_with_period_equal_to_length(self):
        """SMA with period equal to candle count returns single value."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_sma(candles, period=5)

        assert len(result) == 1
        assert result[0][1] == Decimal("100.00")

    def test_sma_different_price_fields(self):
        """SMA should work with different price fields."""
        candles = [
            Candle(
                ticker="TEST",
                date=date.today() - timedelta(days=i),
                open=Decimal("10.00"),
                high=Decimal("20.00"),
                low=Decimal("5.00"),
                close=Decimal("15.00"),
                volume=100000,
            )
            for i in range(4, -1, -1)
        ]

        sma_close = calculate_sma(candles, period=3, price_field="close")
        sma_high = calculate_sma(candles, period=3, price_field="high")
        sma_low = calculate_sma(candles, period=3, price_field="low")
        sma_open = calculate_sma(candles, period=3, price_field="open")

        assert sma_close[0][1] == Decimal("15.00")
        assert sma_high[0][1] == Decimal("20.00")
        assert sma_low[0][1] == Decimal("5.00")
        assert sma_open[0][1] == Decimal("10.00")


class TestSMAEdgeCases:
    """Test SMA edge cases."""

    def test_insufficient_data_returns_empty(self):
        """SMA with period > candles should return empty list."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_sma(candles, period=10)

        assert result == []

    def test_empty_candles_returns_empty(self):
        """SMA with empty candles should return empty list."""
        result = calculate_sma([], period=20)

        assert result == []

    def test_period_one_returns_all_values(self):
        """SMA with period=1 should return all prices (identity)."""
        candles = [
            make_candle("TEST", 2, "10.00"),
            make_candle("TEST", 1, "20.00"),
            make_candle("TEST", 0, "30.00"),
        ]

        result = calculate_sma(candles, period=1)

        assert len(result) == 3
        assert result[0][1] == Decimal("10.00")
        assert result[1][1] == Decimal("20.00")
        assert result[2][1] == Decimal("30.00")

    def test_single_candle_with_period_one(self):
        """Single candle with period=1 should return that value."""
        candles = [make_candle("TEST", 0, "50.00")]

        result = calculate_sma(candles, period=1)

        assert len(result) == 1
        assert result[0][1] == Decimal("50.00")


class TestSMAValidation:
    """Test SMA validation rules."""

    def test_period_zero_raises_error(self):
        """Period = 0 should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_sma(candles, period=0)

    def test_negative_period_raises_error(self):
        """Negative period should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_sma(candles, period=-5)

    def test_invalid_price_field_raises_error(self):
        """Invalid price field should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Invalid price_field"):
            calculate_sma(candles, period=3, price_field="invalid")

    def test_empty_price_field_raises_error(self):
        """Empty price field should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Invalid price_field"):
            calculate_sma(candles, period=3, price_field="")


class TestSMADecimalPrecision:
    """Test SMA maintains Decimal precision."""

    def test_decimal_precision_maintained(self):
        """SMA should maintain Decimal precision."""
        candles = [
            make_candle("TEST", 2, "10.123"),
            make_candle("TEST", 1, "20.456"),
            make_candle("TEST", 0, "30.789"),
        ]

        result = calculate_sma(candles, period=3)

        # (10.123 + 20.456 + 30.789) / 3 = 20.456
        expected = (Decimal("10.123") + Decimal("20.456") + Decimal("30.789")) / 3
        assert result[0][1] == expected
        assert isinstance(result[0][1], Decimal)

    def test_no_floating_point_errors(self):
        """SMA should avoid floating point precision errors."""
        # Values that would cause floating point issues
        candles = [
            make_candle("TEST", 2, "0.1"),
            make_candle("TEST", 1, "0.2"),
            make_candle("TEST", 0, "0.3"),
        ]

        result = calculate_sma(candles, period=3)

        # 0.1 + 0.2 + 0.3 = 0.6, / 3 = 0.2
        # This would fail with floats due to 0.1 + 0.2 != 0.3 issue
        expected = Decimal("0.2")
        assert result[0][1] == expected


class TestSMADeterminism:
    """Test SMA produces deterministic results."""

    def test_same_input_same_output(self):
        """Same inputs should always produce same outputs."""
        candles = [make_candle("TEST", i, f"{i * 10}.00") for i in range(10, -1, -1)]

        result1 = calculate_sma(candles, period=5)
        result2 = calculate_sma(candles, period=5)

        assert result1 == result2

    def test_different_periods_different_results(self):
        """Different periods should produce different results."""
        candles = [make_candle("TEST", i, f"{i * 10}.00") for i in range(10, -1, -1)]

        result_5 = calculate_sma(candles, period=5)
        result_10 = calculate_sma(candles, period=10)

        assert result_5 != result_10
        assert len(result_5) > len(result_10)
