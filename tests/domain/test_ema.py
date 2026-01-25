"""
Tests for EMA indicator.

These tests verify:
- EMA calculation correctness (SMA-seeded initialization)
- EMA formula application
- Edge cases (insufficient data, invalid inputs)
- Decimal precision
- Different price fields
- Determinism

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle
from src.domain.indicators.ema import calculate_ema


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


class TestEMACalculation:
    """Test EMA calculation correctness."""

    def test_first_ema_equals_sma_seed(self):
        """First EMA value should equal SMA of first `period` candles."""
        # Create 5 candles with prices [10, 20, 30, 40, 50]
        candles = [
            make_candle("TEST", 4, "10.00"),
            make_candle("TEST", 3, "20.00"),
            make_candle("TEST", 2, "30.00"),
            make_candle("TEST", 1, "40.00"),
            make_candle("TEST", 0, "50.00"),
        ]

        result = calculate_ema(candles, period=3)

        # First EMA should be SMA of first 3 prices: (10+20+30)/3 = 20
        assert result[0][1] == Decimal("20")

    def test_ema_formula_applied_correctly(self):
        """EMA should apply formula: EMA(t) = Price(t) * k + EMA(t-1) * (1-k)."""
        # Create 5 candles with prices [10, 20, 30, 40, 50]
        candles = [
            make_candle("TEST", 4, "10.00"),
            make_candle("TEST", 3, "20.00"),
            make_candle("TEST", 2, "30.00"),
            make_candle("TEST", 1, "40.00"),
            make_candle("TEST", 0, "50.00"),
        ]

        result = calculate_ema(candles, period=3)

        # k = 2 / (3 + 1) = 0.5
        k = Decimal("0.5")
        one_minus_k = Decimal("0.5")

        # EMA[0] = SMA seed = (10+20+30)/3 = 20
        # EMA[1] = 40 * 0.5 + 20 * 0.5 = 30
        # EMA[2] = 50 * 0.5 + 30 * 0.5 = 40

        assert len(result) == 3
        assert result[0][1] == Decimal("20")  # SMA seed
        assert result[1][1] == Decimal("30")  # First EMA calculation
        assert result[2][1] == Decimal("40")  # Second EMA calculation

    def test_ema_returns_date_and_value_tuples(self):
        """EMA should return tuples of (date, value)."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_ema(candles, period=3)

        assert len(result) == 3
        for date_val, ema_val in result:
            assert isinstance(date_val, date)
            assert isinstance(ema_val, Decimal)

    def test_ema_dates_match_candle_dates(self):
        """EMA dates should match the corresponding candle dates."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_ema(candles, period=3)

        # Result should align with candles starting at index 2 (period-1)
        assert result[0][0] == candles[2].date
        assert result[1][0] == candles[3].date
        assert result[2][0] == candles[4].date

    def test_ema_with_period_equal_to_length(self):
        """EMA with period equal to candle count returns single value (SMA seed only)."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_ema(candles, period=5)

        # Only the SMA seed, no subsequent EMA values
        assert len(result) == 1
        assert result[0][1] == Decimal("100.00")

    def test_ema_different_price_fields(self):
        """EMA should work with different price fields."""
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

        ema_close = calculate_ema(candles, period=3, price_field="close")
        ema_high = calculate_ema(candles, period=3, price_field="high")
        ema_low = calculate_ema(candles, period=3, price_field="low")
        ema_open = calculate_ema(candles, period=3, price_field="open")

        # First EMA value is SMA seed for that field
        assert ema_close[0][1] == Decimal("15.00")
        assert ema_high[0][1] == Decimal("20.00")
        assert ema_low[0][1] == Decimal("5.00")
        assert ema_open[0][1] == Decimal("10.00")

    def test_ema_smoothing_multiplier(self):
        """EMA smoothing multiplier k should be 2/(period+1)."""
        # For period=9, k = 2/10 = 0.2
        # Create simple price series
        candles = [make_candle("TEST", i, "100.00") for i in range(19, -1, -1)]
        candles[9] = make_candle("TEST", 10, "200.00")  # Spike at index 9

        result = calculate_ema(candles, period=9)

        # First value is SMA seed (avg of first 9 candles = 100)
        assert result[0][1] == Decimal("100")

        # Second value includes the spike: EMA = 200 * 0.2 + 100 * 0.8 = 120
        k = Decimal("2") / 10  # 0.2
        expected = Decimal("200") * k + Decimal("100") * (1 - k)
        assert result[1][1] == expected


class TestEMAEdgeCases:
    """Test EMA edge cases."""

    def test_insufficient_data_returns_empty(self):
        """EMA with period > candles should return empty list."""
        candles = [make_candle("TEST", i, "100.00") for i in range(4, -1, -1)]

        result = calculate_ema(candles, period=10)

        assert result == []

    def test_empty_candles_returns_empty(self):
        """EMA with empty candles should return empty list."""
        result = calculate_ema([], period=20)

        assert result == []

    def test_period_one_returns_all_values(self):
        """EMA with period=1 should return all prices (identity)."""
        candles = [
            make_candle("TEST", 2, "10.00"),
            make_candle("TEST", 1, "20.00"),
            make_candle("TEST", 0, "30.00"),
        ]

        result = calculate_ema(candles, period=1)

        # With period=1, k = 2/2 = 1, so EMA = Price (all weight on current)
        assert len(result) == 3
        assert result[0][1] == Decimal("10.00")
        assert result[1][1] == Decimal("20.00")
        assert result[2][1] == Decimal("30.00")

    def test_single_candle_with_period_one(self):
        """Single candle with period=1 should return that value."""
        candles = [make_candle("TEST", 0, "50.00")]

        result = calculate_ema(candles, period=1)

        assert len(result) == 1
        assert result[0][1] == Decimal("50.00")


class TestEMAValidation:
    """Test EMA validation rules."""

    def test_period_zero_raises_error(self):
        """Period = 0 should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_ema(candles, period=0)

    def test_negative_period_raises_error(self):
        """Negative period should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Period must be at least 1"):
            calculate_ema(candles, period=-5)

    def test_invalid_price_field_raises_error(self):
        """Invalid price field should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Invalid price_field"):
            calculate_ema(candles, period=3, price_field="invalid")

    def test_empty_price_field_raises_error(self):
        """Empty price field should raise ValueError."""
        candles = [make_candle("TEST", i, "100.00") for i in range(5)]

        with pytest.raises(ValueError, match="Invalid price_field"):
            calculate_ema(candles, period=3, price_field="")


class TestEMADecimalPrecision:
    """Test EMA maintains Decimal precision."""

    def test_decimal_precision_maintained(self):
        """EMA should maintain Decimal precision."""
        candles = [
            make_candle("TEST", 2, "10.123"),
            make_candle("TEST", 1, "20.456"),
            make_candle("TEST", 0, "30.789"),
        ]

        result = calculate_ema(candles, period=3)

        # First value is SMA seed
        expected_sma = (Decimal("10.123") + Decimal("20.456") + Decimal("30.789")) / 3
        assert result[0][1] == expected_sma
        assert isinstance(result[0][1], Decimal)

    def test_no_floating_point_errors(self):
        """EMA should avoid floating point precision errors."""
        # Values that would cause floating point issues
        candles = [
            make_candle("TEST", 2, "0.1"),
            make_candle("TEST", 1, "0.2"),
            make_candle("TEST", 0, "0.3"),
        ]

        result = calculate_ema(candles, period=3)

        # SMA = (0.1 + 0.2 + 0.3) / 3 = 0.2
        expected = Decimal("0.2")
        assert result[0][1] == expected

    def test_ema_calculation_precision(self):
        """EMA formula should maintain precision through calculations."""
        candles = [
            make_candle("TEST", 3, "100.00"),
            make_candle("TEST", 2, "101.00"),
            make_candle("TEST", 1, "102.00"),
            make_candle("TEST", 0, "103.00"),
        ]

        result = calculate_ema(candles, period=3)

        # k = 2/4 = 0.5
        k = Decimal("0.5")

        # SMA seed = (100 + 101 + 102) / 3 = 101
        sma_seed = (Decimal("100") + Decimal("101") + Decimal("102")) / 3
        assert result[0][1] == sma_seed

        # EMA[1] = 103 * 0.5 + 101 * 0.5 = 102
        expected_ema1 = Decimal("103") * k + sma_seed * (1 - k)
        assert result[1][1] == expected_ema1


class TestEMADeterminism:
    """Test EMA produces deterministic results."""

    def test_same_input_same_output(self):
        """Same inputs should always produce same outputs."""
        candles = [make_candle("TEST", i, f"{i * 10}.00") for i in range(10, -1, -1)]

        result1 = calculate_ema(candles, period=5)
        result2 = calculate_ema(candles, period=5)

        assert result1 == result2

    def test_different_periods_different_results(self):
        """Different periods should produce different results."""
        candles = [make_candle("TEST", i, f"{i * 10}.00") for i in range(10, -1, -1)]

        result_5 = calculate_ema(candles, period=5)
        result_10 = calculate_ema(candles, period=10)

        assert result_5 != result_10
        assert len(result_5) > len(result_10)

    def test_ema_differs_from_sma(self):
        """EMA should differ from SMA for varying price series."""
        # Create non-linear data where EMA and SMA will definitely differ
        # Non-arithmetic progression ensures different results
        candles = [
            make_candle("TEST", 5, "10.00"),
            make_candle("TEST", 4, "15.00"),
            make_candle("TEST", 3, "12.00"),
            make_candle("TEST", 2, "18.00"),
            make_candle("TEST", 1, "25.00"),
            make_candle("TEST", 0, "30.00"),
        ]

        from src.domain.indicators.sma import calculate_sma

        ema_result = calculate_ema(candles, period=3)
        sma_result = calculate_sma(candles, period=3)

        # First values should be the same (EMA seed = SMA)
        # SMA = (10 + 15 + 12) / 3 = 37/3 = 12.333...
        assert ema_result[0][1] == sma_result[0][1]

        # Subsequent values should differ due to different weighting
        # EMA gives more weight to recent prices
        # Check that at least one subsequent value differs
        subsequent_ema = [v for _, v in ema_result[1:]]
        subsequent_sma = [v for _, v in sma_result[1:]]

        # There should be at least one difference
        differences = [e != s for e, s in zip(subsequent_ema, subsequent_sma)]
        assert any(differences), "EMA and SMA should differ for non-uniform price series"
