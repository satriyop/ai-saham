"""Tests for indicator-on-computed-series functions.

Direct tests for apply_indicator_to_series, compute_sma_on_series,
and compute_ema_on_series, independent of FormulaEvaluator.
"""

from decimal import Decimal

import pytest

from src.application.formula.exceptions import FormulaEvaluationError
from src.application.formula.series_indicators import (
    apply_indicator_to_series,
    compute_ema_on_series,
    compute_sma_on_series,
)


class TestComputeSmaOnSeries:
    """Tests for SMA on computed series."""

    def test_sma_basic(self) -> None:
        """SMA produces correct rolling averages."""
        series = [Decimal(str(i)) for i in range(10)]
        result = compute_sma_on_series(series, 3)
        assert len(result) == 8
        assert result[0] == Decimal("1")  # (0+1+2)/3
        assert result[1] == Decimal("2")  # (1+2+3)/3
        assert result[-1] == Decimal("8")  # (7+8+9)/3

    def test_sma_constant_series(self) -> None:
        """SMA of constant series equals that constant."""
        series = [Decimal("100")] * 10
        result = compute_sma_on_series(series, 3)
        assert len(result) == 8
        for val in result:
            assert val == Decimal("100")

    def test_sma_empty_series(self) -> None:
        """Empty series returns empty list."""
        result = compute_sma_on_series([], 10)
        assert result == []

    def test_sma_insufficient_data(self) -> None:
        """Series shorter than period returns empty list."""
        series = [Decimal("1"), Decimal("2")]
        result = compute_sma_on_series(series, 10)
        assert result == []

    def test_sma_period_one(self) -> None:
        """SMA with period 1 returns the series itself."""
        series = [Decimal("10"), Decimal("20"), Decimal("30")]
        result = compute_sma_on_series(series, 1)
        assert result == series

    def test_sma_exact_period(self) -> None:
        """SMA with period equal to series length returns single value."""
        series = [Decimal("1"), Decimal("2"), Decimal("3")]
        result = compute_sma_on_series(series, 3)
        assert result == [Decimal("2")]


class TestComputeEmaOnSeries:
    """Tests for EMA on computed series."""

    def test_ema_constant_series(self) -> None:
        """EMA of constant series equals that constant."""
        series = [Decimal("100")] * 10
        result = compute_ema_on_series(series, 3)
        assert len(result) == 8
        for val in result:
            assert val == Decimal("100")

    def test_ema_empty_series(self) -> None:
        """Empty series returns empty list."""
        result = compute_ema_on_series([], 10)
        assert result == []

    def test_ema_insufficient_data(self) -> None:
        """Series shorter than period returns empty list."""
        series = [Decimal("1"), Decimal("2")]
        result = compute_ema_on_series(series, 10)
        assert result == []

    def test_ema_uses_sma_seed(self) -> None:
        """EMA first value equals SMA of first period values."""
        series = [Decimal(str(i)) for i in range(10)]
        period = 3
        result = compute_ema_on_series(series, period)
        expected_first = sum(series[:period]) / period
        assert result[0] == expected_first

    def test_ema_not_constant(self) -> None:
        """EMA of trending series converges toward later values."""
        series = [Decimal(str(i)) for i in range(10)]
        period = 3
        result = compute_ema_on_series(series, period)
        assert len(result) == 8
        # Values should be increasing, following the trend
        for i in range(1, len(result)):
            assert result[i] > result[i - 1]


class TestApplyIndicatorToSeries:
    """Tests for the dispatcher apply_indicator_to_series."""

    def test_sma_dispatched(self) -> None:
        """SMA name dispatches to compute_sma_on_series."""
        series = [Decimal(str(i)) for i in range(10)]
        result = apply_indicator_to_series("SMA", series, 3)
        expected = compute_sma_on_series(series, 3)
        assert result == expected

    def test_ema_dispatched(self) -> None:
        """EMA name dispatches to compute_ema_on_series."""
        series = [Decimal(str(i)) for i in range(10)]
        result = apply_indicator_to_series("EMA", series, 3)
        expected = compute_ema_on_series(series, 3)
        assert result == expected

    def test_empty_series(self) -> None:
        """Empty series returns empty list."""
        result = apply_indicator_to_series("SMA", [], 10)
        assert result == []

    def test_unsupported_indicator(self) -> None:
        """Unsupported indicator raises FormulaEvaluationError."""
        series = [Decimal(str(i)) for i in range(10)]
        with pytest.raises(FormulaEvaluationError) as exc_info:
            apply_indicator_to_series("RSI", series, 14)
        msg = str(exc_info.value)
        assert "RSI" in msg
        assert "Only SMA and EMA" in msg

    def test_unsupported_indicator_error_has_formula_name(self) -> None:
        """Error includes formula_name attribute."""
        series = [Decimal(str(i)) for i in range(10)]
        with pytest.raises(FormulaEvaluationError) as exc_info:
            apply_indicator_to_series("RSI", series, 14)
        assert exc_info.value.formula_name == "RSI"
