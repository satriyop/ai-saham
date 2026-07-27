"""Tests for the formula evaluator."""

from decimal import Decimal

import pytest

from src.application.formula.evaluator import FormulaEvaluator
from src.application.formula.exceptions import FormulaEvaluationError
from src.application.formula.parser import parse


class MockSeriesProvider:
    """Mock series provider for testing."""

    def __init__(
        self,
        series_data: dict[str, list[Decimal]] | None = None,
        indicator_data: dict[tuple[str, int], list[Decimal]] | None = None,
        default_periods: dict[str, int] | None = None,
    ) -> None:
        self._series_data = series_data or {}
        self._indicator_data = indicator_data or {}
        self._default_periods = default_periods or {
            "SMA": 20,
            "EMA": 20,
            "RSI": 14,
        }

    def get_series(self, name: str) -> list[Decimal]:
        name_upper = name.upper()
        if name_upper in self._series_data:
            return self._series_data[name_upper]
        raise ValueError(f"Unknown series: {name}")

    def compute_indicator(self, name: str, period: int) -> list[Decimal]:
        key = (name.upper(), period)
        if key in self._indicator_data:
            return self._indicator_data[key]
        raise ValueError(f"Unknown indicator: {name}({period})")

    def get_default_period(self, name: str) -> int:
        name_upper = name.upper()
        if name_upper in self._default_periods:
            return self._default_periods[name_upper]
        raise ValueError(f"Unknown indicator: {name}")


class TestEvaluateNumber:
    """Tests for evaluating number nodes."""

    def test_number_returns_single_element_list(self) -> None:
        """Test that number evaluates to single-element list."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("42")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("42")]

    def test_decimal_number(self) -> None:
        """Test evaluating decimal number."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("0.5")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("0.5")]


class TestEvaluateSeries:
    """Tests for evaluating series nodes."""

    def test_close_series(self) -> None:
        """Test evaluating CLOSE series."""
        close_values = [Decimal(str(i)) for i in range(10)]
        provider = MockSeriesProvider(series_data={"CLOSE": close_values})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE")

        result = evaluator.compute(ast, candle_count=10)
        assert result == close_values

    def test_volume_series(self) -> None:
        """Test evaluating VOLUME series."""
        volume_values = [Decimal(str(i * 1000)) for i in range(5)]
        provider = MockSeriesProvider(series_data={"VOLUME": volume_values})
        evaluator = FormulaEvaluator(provider)
        ast = parse("VOLUME")

        result = evaluator.compute(ast, candle_count=5)
        assert result == volume_values


class TestEvaluateFunctionCalls:
    """Tests for evaluating function calls."""

    def test_function_with_period(self) -> None:
        """Test evaluating function with explicit period."""
        rsi_values = [Decimal(str(50 + i)) for i in range(10)]
        provider = MockSeriesProvider(indicator_data={("RSI", 14): rsi_values})
        evaluator = FormulaEvaluator(provider)
        ast = parse("RSI(14)")

        result = evaluator.compute(ast, candle_count=100)
        assert result == rsi_values

    def test_function_with_series_and_period(self) -> None:
        """Test evaluating function with series and period."""
        close_values = [Decimal(str(100 + i)) for i in range(20)]
        sma_values = [Decimal(str(105 + i)) for i in range(10)]

        provider = MockSeriesProvider(
            series_data={"CLOSE": close_values}, indicator_data={("SMA", 10): sma_values}
        )
        evaluator = FormulaEvaluator(provider)
        ast = parse("SMA(CLOSE, 10)")

        # SMA on CLOSE should compute internally
        result = evaluator.compute(ast, candle_count=20)
        # Result should have length = len(close) - period + 1 = 11
        assert len(result) == 11


class TestEvaluateBinaryOperations:
    """Tests for evaluating binary operations."""

    def test_number_addition(self) -> None:
        """Test adding two numbers."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("1 + 2")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("3")]

    def test_number_subtraction(self) -> None:
        """Test subtracting numbers."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("10 - 4")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("6")]

    def test_number_multiplication(self) -> None:
        """Test multiplying numbers."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("3 * 4")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("12")]

    def test_number_division(self) -> None:
        """Test dividing numbers."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("10 / 2")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("5")]

    def test_division_by_zero(self) -> None:
        """Test division by zero returns 0."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("10 / 0")

        result = evaluator.compute(ast, candle_count=100)
        assert result == [Decimal("0")]

    def test_series_addition(self) -> None:
        """Test adding two series."""
        series1 = [Decimal("1"), Decimal("2"), Decimal("3")]
        series2 = [Decimal("10"), Decimal("20"), Decimal("30")]

        provider = MockSeriesProvider(series_data={"CLOSE": series1, "OPEN": series2})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE + OPEN")

        result = evaluator.compute(ast, candle_count=3)
        assert result == [Decimal("11"), Decimal("22"), Decimal("33")]

    def test_series_subtraction(self) -> None:
        """Test subtracting series."""
        series1 = [Decimal("10"), Decimal("20"), Decimal("30")]
        series2 = [Decimal("1"), Decimal("2"), Decimal("3")]

        provider = MockSeriesProvider(series_data={"CLOSE": series1, "OPEN": series2})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE - OPEN")

        result = evaluator.compute(ast, candle_count=3)
        assert result == [Decimal("9"), Decimal("18"), Decimal("27")]

    def test_series_multiplication(self) -> None:
        """Test multiplying series (e.g., dollar volume)."""
        close = [Decimal("100"), Decimal("101"), Decimal("102")]
        volume = [Decimal("1000"), Decimal("2000"), Decimal("3000")]

        provider = MockSeriesProvider(series_data={"CLOSE": close, "VOLUME": volume})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE * VOLUME")

        result = evaluator.compute(ast, candle_count=3)
        assert result == [Decimal("100000"), Decimal("202000"), Decimal("306000")]

    def test_scalar_broadcast_left(self) -> None:
        """Test scalar broadcast when left operand is scalar."""
        series = [Decimal("1"), Decimal("2"), Decimal("3")]

        provider = MockSeriesProvider(series_data={"CLOSE": series})
        evaluator = FormulaEvaluator(provider)
        ast = parse("10 + CLOSE")

        result = evaluator.compute(ast, candle_count=3)
        assert result == [Decimal("11"), Decimal("12"), Decimal("13")]

    def test_scalar_broadcast_right(self) -> None:
        """Test scalar broadcast when right operand is scalar."""
        series = [Decimal("10"), Decimal("20"), Decimal("30")]

        provider = MockSeriesProvider(series_data={"CLOSE": series})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE / 2")

        result = evaluator.compute(ast, candle_count=3)
        assert result == [Decimal("5"), Decimal("10"), Decimal("15")]

    def test_different_length_series_alignment(self) -> None:
        """Test alignment when series have different lengths."""
        # Longer series
        series1 = [Decimal(str(i)) for i in range(10)]
        # Shorter series
        series2 = [Decimal(str(i * 10)) for i in range(5)]

        provider = MockSeriesProvider(series_data={"CLOSE": series1, "OPEN": series2})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE + OPEN")

        result = evaluator.compute(ast, candle_count=10)
        # Result should have length = min(10, 5) = 5
        # Aligned from end: series1[-5:] + series2[-5:]
        assert len(result) == 5


class TestEvaluateSMAOnSeries:
    """Tests for SMA applied to computed series."""

    def test_sma_on_series(self) -> None:
        """Test SMA computed on an input series."""
        # Create 10 values
        series = [Decimal(str(i)) for i in range(10)]  # 0,1,2,3,4,5,6,7,8,9

        provider = MockSeriesProvider(series_data={"CLOSE": series})
        evaluator = FormulaEvaluator(provider)
        ast = parse("SMA(CLOSE, 3)")

        result = evaluator.compute(ast, candle_count=10)

        # SMA(3) on [0,1,2,3,4,5,6,7,8,9] should give:
        # (0+1+2)/3=1, (1+2+3)/3=2, (2+3+4)/3=3, etc.
        assert len(result) == 8  # 10 - 3 + 1
        assert result[0] == Decimal("1")  # (0+1+2)/3
        assert result[1] == Decimal("2")  # (1+2+3)/3


class TestEvaluateEMAOnSeries:
    """Tests for EMA applied to computed series."""

    def test_ema_on_series(self) -> None:
        """Test EMA computed on an input series."""
        # Create constant series for predictable result
        series = [Decimal("100")] * 10

        provider = MockSeriesProvider(series_data={"CLOSE": series})
        evaluator = FormulaEvaluator(provider)
        ast = parse("EMA(CLOSE, 3)")

        result = evaluator.compute(ast, candle_count=10)

        # EMA of constant series should equal that constant
        assert len(result) == 8  # 10 - 3 + 1
        # All values should be close to 100
        for val in result:
            assert val == Decimal("100")


class TestEvaluateComplexFormulas:
    """Tests for complex formula evaluation."""

    def test_macd_like_formula(self) -> None:
        """Test MACD-like formula: EMA(12) - EMA(26)."""
        close_values = [Decimal("100")] * 30  # Constant for predictability

        provider = MockSeriesProvider(series_data={"CLOSE": close_values})
        evaluator = FormulaEvaluator(provider)
        ast = parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)")

        result = evaluator.compute(ast, candle_count=30)

        # For constant series, EMA(12) = EMA(26) = 100, so difference = 0
        for val in result:
            assert val == Decimal("0")

    def test_average_of_smas(self) -> None:
        """Test (SMA(10) + SMA(20)) / 2."""
        # Use constant series for predictability
        close_values = [Decimal("100")] * 25

        provider = MockSeriesProvider(series_data={"CLOSE": close_values})
        evaluator = FormulaEvaluator(provider)
        ast = parse("(SMA(CLOSE, 10) + SMA(CLOSE, 20)) / 2")

        result = evaluator.compute(ast, candle_count=25)

        # For constant series, SMA = 100, so average = 100
        for val in result:
            assert val == Decimal("100")


class TestEvaluatorEdgeCases:
    """Tests for edge cases in evaluation."""

    def test_empty_series(self) -> None:
        """Test evaluation with empty series."""
        provider = MockSeriesProvider(series_data={"CLOSE": []})
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE")

        result = evaluator.compute(ast, candle_count=0)
        assert result == []

    def test_insufficient_data_for_sma(self) -> None:
        """Test SMA with insufficient data."""
        # Only 2 values but period is 10
        series = [Decimal("1"), Decimal("2")]

        provider = MockSeriesProvider(series_data={"CLOSE": series})
        evaluator = FormulaEvaluator(provider)
        ast = parse("SMA(CLOSE, 10)")

        result = evaluator.compute(ast, candle_count=2)
        assert result == []  # Not enough data

    def test_candle_count_zero(self) -> None:
        """Test with zero candle count."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("42")

        # Still works for pure numbers
        result = evaluator.compute(ast, candle_count=0)
        assert result == [Decimal("42")]


class TestEvaluatorErrors:
    """Tests for evaluator error handling."""

    def test_unknown_indicator(self) -> None:
        """Test error on unknown indicator."""
        provider = MockSeriesProvider()
        evaluator = FormulaEvaluator(provider)
        ast = parse("UNKNOWN(14)")

        with pytest.raises(FormulaEvaluationError):
            evaluator.compute(ast, candle_count=100)

    def test_invalid_series_name(self) -> None:
        """Test error on invalid series name through provider."""
        provider = MockSeriesProvider(series_data={})  # Empty
        evaluator = FormulaEvaluator(provider)
        ast = parse("CLOSE")

        with pytest.raises((FormulaEvaluationError, ValueError)):
            evaluator.compute(ast, candle_count=100)
