"""Integration tests for the formula module.

Tests end-to-end formula parsing, validation, and evaluation
using the IndicatorRegistry.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.formula import (
    FormulaValidationError,
    parse,
    validate_formulas,
)
from src.application.services.indicator_registry import (
    FormulaRegistrationError,
    IndicatorRegistry,
)
from src.domain.entities.candle import Candle


def make_candle(
    day_offset: int,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 10000,
) -> Candle:
    """Helper to create a test candle."""
    return Candle(
        ticker="TEST",
        date=date(2024, 1, 1) + timedelta(days=day_offset),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def make_trending_candles(count: int, start_price: float = 100.0) -> list[Candle]:
    """Create candles with an upward trend."""
    return [
        make_candle(
            i,
            open_=start_price + i,
            high=start_price + i + 2,
            low=start_price + i - 1,
            close=start_price + i + 1,
            volume=10000 + i * 100,
        )
        for i in range(count)
    ]


class TestFormulaRegistration:
    """Tests for registering formulas in the registry."""

    def test_register_simple_formula(self) -> None:
        """Test registering a simple formula."""
        registry = IndicatorRegistry()
        ast = parse("SMA(RSI(14), 10)")
        registry.register_formula("SMOOTH_RSI", ast)

        assert registry.is_registered("SMOOTH_RSI")
        assert "SMOOTH_RSI" in registry.list_formulas()

    def test_register_multiple_formulas(self) -> None:
        """Test registering multiple formulas."""
        registry = IndicatorRegistry()

        formulas = {
            "MACD_LINE": parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)"),
            "SMOOTH_RSI": parse("SMA(RSI(14), 10)"),
        }

        for name, ast in formulas.items():
            registry.register_formula(name, ast)

        assert len(registry.list_formulas()) == 2
        assert registry.is_registered("MACD_LINE")
        assert registry.is_registered("SMOOTH_RSI")

    def test_register_formula_conflicts_with_builtin(self) -> None:
        """Test that formula cannot shadow built-in."""
        registry = IndicatorRegistry()
        ast = parse("RSI(14)")

        with pytest.raises(FormulaRegistrationError) as exc_info:
            registry.register_formula("SMA", ast)

        assert "conflicts with built-in" in str(exc_info.value)

    def test_register_duplicate_formula(self) -> None:
        """Test that duplicate formula registration fails."""
        registry = IndicatorRegistry()
        ast = parse("RSI(14)")

        registry.register_formula("MY_INDICATOR", ast)

        with pytest.raises(FormulaRegistrationError) as exc_info:
            registry.register_formula("MY_INDICATOR", ast)

        assert "already registered" in str(exc_info.value)

    def test_formula_case_insensitive(self) -> None:
        """Test that formula names are case-insensitive."""
        registry = IndicatorRegistry()
        ast = parse("RSI(14)")

        registry.register_formula("my_indicator", ast)

        assert registry.is_registered("MY_INDICATOR")
        assert registry.is_registered("my_indicator")


class TestFormulaComputation:
    """Tests for computing formula values via registry."""

    def test_compute_sma_of_rsi(self) -> None:
        """Test computing SMA(RSI(14), 10) formula."""
        registry = IndicatorRegistry()
        ast = parse("SMA(RSI(14), 10)")
        registry.register_formula("SMOOTH_RSI", ast)

        candles = make_trending_candles(100)
        result = registry.compute("SMOOTH_RSI", candles, period=0)

        assert len(result) > 0
        # All values should have dates
        for dt, val in result:
            assert isinstance(dt, date)
            assert isinstance(val, Decimal)

    def test_compute_macd_line(self) -> None:
        """Test computing MACD-like formula."""
        registry = IndicatorRegistry()
        ast = parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)")
        registry.register_formula("MACD_LINE", ast)

        candles = make_trending_candles(50)
        result = registry.compute("MACD_LINE", candles, period=0)

        assert len(result) > 0
        # For trending candles, MACD should be positive (faster EMA > slower EMA)
        for _, val in result:
            assert val > 0

    def test_compute_close_times_volume(self) -> None:
        """Test computing CLOSE * VOLUME (dollar volume)."""
        registry = IndicatorRegistry()
        ast = parse("CLOSE * VOLUME")
        registry.register_formula("DOLLAR_VOLUME", ast)

        candles = [
            make_candle(0, close=100.0, volume=1000),
            make_candle(1, close=101.0, volume=2000),
            make_candle(2, close=102.0, volume=3000),
        ]
        result = registry.compute("DOLLAR_VOLUME", candles, period=0)

        assert len(result) == 3
        assert result[0][1] == Decimal("100") * Decimal("1000")
        assert result[1][1] == Decimal("101") * Decimal("2000")
        assert result[2][1] == Decimal("102") * Decimal("3000")

    def test_compute_formula_empty_candles(self) -> None:
        """Test computing formula with empty candles."""
        registry = IndicatorRegistry()
        ast = parse("SMA(CLOSE, 20)")
        registry.register_formula("TEST", ast)

        result = registry.compute("TEST", [], period=0)
        assert result == []

    def test_compute_formula_insufficient_data(self) -> None:
        """Test computing formula with insufficient data."""
        registry = IndicatorRegistry()
        # SMA(RSI(14), 10) needs at least 14+1 candles for RSI, then 10 more for SMA
        ast = parse("SMA(RSI(14), 10)")
        registry.register_formula("SMOOTH_RSI", ast)

        candles = make_trending_candles(10)  # Not enough
        result = registry.compute("SMOOTH_RSI", candles, period=0)

        # Should return empty or very few results
        assert len(result) <= 10


class TestFormulaValidation:
    """Tests for formula validation integration."""

    def test_validate_valid_formulas(self) -> None:
        """Test validating formulas against registry."""
        registry = IndicatorRegistry()
        formulas = {
            "SMOOTH_RSI": parse("SMA(RSI(14), 10)"),
        }

        available = registry.get_available_indicators()
        order = validate_formulas(formulas, available)

        assert order == ["SMOOTH_RSI"]

    def test_validate_formula_chain(self) -> None:
        """Test validating formula that depends on another formula."""
        registry = IndicatorRegistry()

        # First register A so B can reference it
        ast_a = parse("RSI(14)")
        registry.register_formula("A", ast_a)

        # Now validate B which references A
        formulas = {
            "B": parse("SMA(A, 10)"),
        }

        available = registry.get_available_indicators()
        order = validate_formulas(formulas, available)

        assert order == ["B"]

    def test_validate_unknown_reference(self) -> None:
        """Test validation error on unknown reference."""
        registry = IndicatorRegistry()
        formulas = {
            "TEST": parse("UNKNOWN_INDICATOR(14)"),
        }

        available = registry.get_available_indicators()
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formulas(formulas, available)

        assert "Unknown indicator" in str(exc_info.value)


class TestFormulaDateAlignment:
    """Tests for date alignment in formula results."""

    def test_dates_are_aligned(self) -> None:
        """Test that formula results have correct date alignment."""
        registry = IndicatorRegistry()
        ast = parse("SMA(CLOSE, 5)")
        registry.register_formula("SMA5", ast)

        candles = make_trending_candles(20)
        result = registry.compute("SMA5", candles, period=0)

        # Result dates should be from candles
        result_dates = [dt for dt, _ in result]
        candle_dates = [c.date for c in candles]

        # All result dates should be in candle dates
        for dt in result_dates:
            assert dt in candle_dates

        # Results should be aligned to end (last result date = last candle date)
        if result:
            assert result[-1][0] == candles[-1].date

    def test_binary_op_alignment(self) -> None:
        """Test date alignment for binary operations."""
        registry = IndicatorRegistry()
        # EMA(12) produces more values than EMA(26)
        ast = parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)")
        registry.register_formula("MACD", ast)

        candles = make_trending_candles(50)
        result = registry.compute("MACD", candles, period=0)

        # Result should align with shorter series (EMA26)
        # EMA(26) produces 50 - 26 + 1 = 25 values
        assert len(result) <= 25

        # Last date should be last candle date
        if result:
            assert result[-1][0] == candles[-1].date


class TestFormulaListMethods:
    """Tests for registry list methods with formulas."""

    def test_list_indicators_includes_formulas(self) -> None:
        """Test that list_indicators includes registered formulas."""
        registry = IndicatorRegistry()
        ast = parse("RSI(14)")
        registry.register_formula("MY_RSI", ast)

        indicators = registry.list_indicators()
        assert "MY_RSI" in indicators
        # Built-ins should also be there
        assert "SMA" in indicators
        assert "EMA" in indicators
        assert "RSI" in indicators

    def test_list_formulas_only_formulas(self) -> None:
        """Test that list_formulas returns only formulas."""
        registry = IndicatorRegistry()
        registry.register_formula("A", parse("RSI(14)"))
        registry.register_formula("B", parse("SMA(CLOSE, 20)"))

        formulas = registry.list_formulas()
        assert set(formulas) == {"A", "B"}
        # Built-ins should not be in formulas list
        assert "SMA" not in formulas

    def test_get_available_indicators(self) -> None:
        """Test get_available_indicators includes all types."""
        registry = IndicatorRegistry()
        registry.register_formula("CUSTOM", parse("RSI(14)"))

        available = registry.get_available_indicators()
        assert "SMA" in available  # Built-in
        assert "EMA" in available  # Built-in
        assert "RSI" in available  # Built-in
        assert "CUSTOM" in available  # Formula


class TestFormulaPeriod:
    """Tests for formula period handling."""

    def test_formula_default_period_is_zero(self) -> None:
        """Test that formulas have default period of 0."""
        registry = IndicatorRegistry()
        registry.register_formula("TEST", parse("RSI(14)"))

        period = registry.get_default_period("TEST")
        assert period == 0

    def test_compute_ignores_period_for_formula(self) -> None:
        """Test that period parameter is ignored for formulas."""
        registry = IndicatorRegistry()
        ast = parse("SMA(CLOSE, 10)")  # Period embedded in formula
        registry.register_formula("SMA10", ast)

        candles = make_trending_candles(30)

        # These should produce same results regardless of period argument
        result1 = registry.compute("SMA10", candles, period=0)
        result2 = registry.compute("SMA10", candles, period=999)

        assert result1 == result2
