"""Tests for series binary operations.

Direct tests for apply_binary_op, independent of FormulaEvaluator.
"""

from decimal import Decimal

from src.application.formula.series_ops import apply_binary_op


class TestScalarBroadcast:
    """Tests for scalar broadcasting."""

    def test_scalar_left_broadcast(self) -> None:
        """Scalar on left broadcasts to match right series length."""
        result = apply_binary_op("+", [Decimal("10")], [Decimal("1"), Decimal("2"), Decimal("3")])
        assert result == [Decimal("11"), Decimal("12"), Decimal("13")]

    def test_scalar_right_broadcast(self) -> None:
        """Scalar on right broadcasts to match left series length."""
        result = apply_binary_op("/", [Decimal("10"), Decimal("20"), Decimal("30")], [Decimal("2")])
        assert result == [Decimal("5"), Decimal("10"), Decimal("15")]

    def test_both_scalar(self) -> None:
        """Two scalars produce single-element result."""
        result = apply_binary_op("+", [Decimal("3")], [Decimal("4")])
        assert result == [Decimal("7")]


class TestEndAlignment:
    """Tests for end-alignment of different-length series."""

    def test_different_lengths(self) -> None:
        """Result length is min of operand lengths, aligned from end."""
        left = [Decimal(str(i)) for i in range(10)]
        right = [Decimal(str(i * 10)) for i in range(5)]
        result = apply_binary_op("+", left, right)
        assert len(result) == 5
        # left[-5:] = [5,6,7,8,9], right[-5:] = [0,10,20,30,40]
        assert result == [Decimal("5"), Decimal("16"), Decimal("27"), Decimal("38"), Decimal("49")]

    def test_equal_lengths(self) -> None:
        """Equal lengths produce same-length result."""
        left = [Decimal("1"), Decimal("2"), Decimal("3")]
        right = [Decimal("10"), Decimal("20"), Decimal("30")]
        result = apply_binary_op("+", left, right)
        assert result == [Decimal("11"), Decimal("22"), Decimal("33")]

    def test_empty_left(self) -> None:
        """Empty left series returns empty list."""
        result = apply_binary_op("+", [], [Decimal("1"), Decimal("2")])
        assert result == []

    def test_empty_right(self) -> None:
        """Empty right series returns empty list."""
        result = apply_binary_op("+", [Decimal("1"), Decimal("2")], [])
        assert result == []

    def test_both_empty(self) -> None:
        """Both empty returns empty list."""
        result = apply_binary_op("+", [], [])
        assert result == []


class TestArithmeticOperations:
    """Tests for each arithmetic operation."""

    def test_addition(self) -> None:
        result = apply_binary_op("+", [Decimal("1"), Decimal("2")], [Decimal("10"), Decimal("20")])
        assert result == [Decimal("11"), Decimal("22")]

    def test_subtraction(self) -> None:
        result = apply_binary_op("-", [Decimal("10"), Decimal("20")], [Decimal("1"), Decimal("2")])
        assert result == [Decimal("9"), Decimal("18")]

    def test_multiplication(self) -> None:
        result = apply_binary_op("*", [Decimal("3"), Decimal("4")], [Decimal("5"), Decimal("6")])
        assert result == [Decimal("15"), Decimal("24")]

    def test_division(self) -> None:
        result = apply_binary_op("/", [Decimal("10"), Decimal("20")], [Decimal("2"), Decimal("4")])
        assert result == [Decimal("5"), Decimal("5")]


class TestDivisionByZero:
    """Tests for division-by-zero handling."""

    def test_division_by_zero_returns_zero(self) -> None:
        """Division by zero returns Decimal('0')."""
        result = apply_binary_op("/", [Decimal("10")], [Decimal("0")])
        assert result == [Decimal("0")]

    def test_mixed_division(self) -> None:
        """Valid divisions and zero divisions in mixed series."""
        result = apply_binary_op(
            "/",
            [Decimal("10"), Decimal("20"), Decimal("30")],
            [Decimal("2"), Decimal("0"), Decimal("5")],
        )
        assert result == [Decimal("5"), Decimal("0"), Decimal("6")]


class TestUnsupportedOperator:
    """Tests for unsupported operators."""

    def test_unsupported_operator_returns_empty(self) -> None:
        """Unknown operator produces no appended values (current behavior)."""
        result = apply_binary_op("%", [Decimal("1"), Decimal("2")], [Decimal("3"), Decimal("4")])
        assert result == []
