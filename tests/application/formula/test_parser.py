"""Tests for the formula parser."""

from decimal import Decimal

import pytest

from src.application.formula.ast_nodes import (
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.exceptions import FormulaParseError
from src.application.formula.parser import parse


class TestParseNumbers:
    """Tests for parsing numeric literals."""

    def test_integer(self) -> None:
        """Test parsing integer."""
        ast = parse("14")
        assert isinstance(ast, NumberNode)
        assert ast.value == Decimal("14")

    def test_decimal(self) -> None:
        """Test parsing decimal number."""
        ast = parse("0.5")
        assert isinstance(ast, NumberNode)
        assert ast.value == Decimal("0.5")

    def test_large_number(self) -> None:
        """Test parsing large number."""
        ast = parse("1000000")
        assert isinstance(ast, NumberNode)
        assert ast.value == Decimal("1000000")


class TestParseSeries:
    """Tests for parsing series keywords."""

    @pytest.mark.parametrize(
        "keyword,expected_field",
        [
            ("CLOSE", "close"),
            ("close", "close"),
            ("OPEN", "open"),
            ("HIGH", "high"),
            ("LOW", "low"),
            ("VOLUME", "volume"),
        ],
    )
    def test_series_keywords(self, keyword: str, expected_field: str) -> None:
        """Test parsing series keywords (case-insensitive)."""
        ast = parse(keyword)
        assert isinstance(ast, SeriesNode)
        assert ast.field == expected_field


class TestParseFunctionCalls:
    """Tests for parsing function calls."""

    def test_function_no_args(self) -> None:
        """Test parsing function with no arguments."""
        ast = parse("RSI")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "RSI"
        assert ast.arguments == ()

    def test_function_single_number_arg(self) -> None:
        """Test parsing function with single number argument."""
        ast = parse("RSI(14)")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "RSI"
        assert len(ast.arguments) == 1
        assert isinstance(ast.arguments[0], NumberNode)
        assert ast.arguments[0].value == Decimal("14")

    def test_function_two_args(self) -> None:
        """Test parsing function with two arguments."""
        ast = parse("SMA(CLOSE, 20)")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "SMA"
        assert len(ast.arguments) == 2
        assert isinstance(ast.arguments[0], SeriesNode)
        assert ast.arguments[0].field == "close"
        assert isinstance(ast.arguments[1], NumberNode)
        assert ast.arguments[1].value == Decimal("20")

    def test_nested_function(self) -> None:
        """Test parsing nested function calls."""
        ast = parse("SMA(RSI(14), 10)")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "SMA"
        assert len(ast.arguments) == 2

        # First arg is RSI(14)
        inner = ast.arguments[0]
        assert isinstance(inner, FunctionCallNode)
        assert inner.name == "RSI"
        assert len(inner.arguments) == 1
        assert isinstance(inner.arguments[0], NumberNode)
        assert inner.arguments[0].value == Decimal("14")

        # Second arg is 10
        assert isinstance(ast.arguments[1], NumberNode)
        assert ast.arguments[1].value == Decimal("10")

    def test_function_name_case_insensitive(self) -> None:
        """Test that function names are normalized to uppercase."""
        ast = parse("sma(close, 20)")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "SMA"


class TestParseBinaryOperations:
    """Tests for parsing binary operations."""

    def test_addition(self) -> None:
        """Test parsing addition."""
        ast = parse("1 + 2")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "+"
        assert isinstance(ast.left, NumberNode)
        assert isinstance(ast.right, NumberNode)

    def test_subtraction(self) -> None:
        """Test parsing subtraction."""
        ast = parse("10 - 5")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "-"

    def test_multiplication(self) -> None:
        """Test parsing multiplication."""
        ast = parse("3 * 4")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "*"

    def test_division(self) -> None:
        """Test parsing division."""
        ast = parse("10 / 2")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "/"

    def test_operator_precedence_mul_over_add(self) -> None:
        """Test that * has higher precedence than +."""
        # 1 + 2 * 3 should be 1 + (2 * 3)
        ast = parse("1 + 2 * 3")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "+"
        assert isinstance(ast.left, NumberNode)
        assert ast.left.value == Decimal("1")

        right = ast.right
        assert isinstance(right, BinaryOpNode)
        assert right.operator == "*"

    def test_operator_precedence_div_over_sub(self) -> None:
        """Test that / has higher precedence than -."""
        # 10 - 4 / 2 should be 10 - (4 / 2)
        ast = parse("10 - 4 / 2")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "-"

        right = ast.right
        assert isinstance(right, BinaryOpNode)
        assert right.operator == "/"

    def test_left_to_right_associativity(self) -> None:
        """Test left-to-right associativity for same precedence."""
        # 1 - 2 - 3 should be (1 - 2) - 3
        ast = parse("1 - 2 - 3")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "-"

        left = ast.left
        assert isinstance(left, BinaryOpNode)
        assert left.operator == "-"

        assert isinstance(ast.right, NumberNode)
        assert ast.right.value == Decimal("3")

    def test_parentheses_override_precedence(self) -> None:
        """Test that parentheses override operator precedence."""
        # (1 + 2) * 3 should be (1 + 2) * 3
        ast = parse("(1 + 2) * 3")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "*"

        left = ast.left
        assert isinstance(left, BinaryOpNode)
        assert left.operator == "+"


class TestParseComplexFormulas:
    """Tests for parsing complex formulas."""

    def test_macd_line(self) -> None:
        """Test parsing MACD-like formula."""
        ast = parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "-"

        assert isinstance(ast.left, FunctionCallNode)
        assert ast.left.name == "EMA"

        assert isinstance(ast.right, FunctionCallNode)
        assert ast.right.name == "EMA"

    def test_average_of_smas(self) -> None:
        """Test parsing average of two SMAs."""
        ast = parse("(SMA(CLOSE, 10) + SMA(CLOSE, 20)) / 2")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "/"

        assert isinstance(ast.left, BinaryOpNode)
        assert ast.left.operator == "+"

        assert isinstance(ast.right, NumberNode)
        assert ast.right.value == Decimal("2")

    def test_dollar_volume(self) -> None:
        """Test parsing CLOSE * VOLUME."""
        ast = parse("CLOSE * VOLUME")
        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "*"
        assert isinstance(ast.left, SeriesNode)
        assert ast.left.field == "close"
        assert isinstance(ast.right, SeriesNode)
        assert ast.right.field == "volume"

    def test_deeply_nested(self) -> None:
        """Test parsing deeply nested formula."""
        ast = parse("SMA(EMA(RSI(14), 5), 10)")
        assert isinstance(ast, FunctionCallNode)
        assert ast.name == "SMA"

        inner = ast.arguments[0]
        assert isinstance(inner, FunctionCallNode)
        assert inner.name == "EMA"

        innermost = inner.arguments[0]
        assert isinstance(innermost, FunctionCallNode)
        assert innermost.name == "RSI"


class TestParserErrors:
    """Tests for parser error handling."""

    def test_empty_string(self) -> None:
        """Test error on empty string."""
        with pytest.raises(FormulaParseError) as exc_info:
            parse("")
        assert "Expected expression" in str(exc_info.value)

    def test_missing_closing_paren(self) -> None:
        """Test error on missing closing parenthesis."""
        with pytest.raises(FormulaParseError) as exc_info:
            parse("SMA(CLOSE, 20")
        assert "Expected ')'" in str(exc_info.value)

    def test_missing_operand(self) -> None:
        """Test error on missing operand."""
        with pytest.raises(FormulaParseError):
            parse("1 + ")

    def test_unexpected_token(self) -> None:
        """Test error on unexpected token."""
        with pytest.raises(FormulaParseError) as exc_info:
            parse("SMA(CLOSE, 20) extra")
        assert "Unexpected token" in str(exc_info.value)

    def test_missing_argument(self) -> None:
        """Test error on missing function argument after comma."""
        with pytest.raises(FormulaParseError):
            parse("SMA(CLOSE, )")

    def test_double_operator(self) -> None:
        """Test error on consecutive operators."""
        with pytest.raises(FormulaParseError):
            parse("1 + + 2")
