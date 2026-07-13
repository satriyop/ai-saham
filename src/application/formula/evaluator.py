"""AST evaluation for formula expressions.

Application layer - Formula evaluator.

This module evaluates parsed formula ASTs to produce index-aligned series
of Decimal values. The evaluator delegates to the IndicatorRegistry for
indicator computation and price data access.

Key design decisions:
- All series are index-aligned (aligned to end of candles)
- Binary operations result in length = min(len(left), len(right))
- Division by zero returns Decimal("0") with a warning log
- Numbers are broadcast to series length when combined with series

Example:
    >>> evaluator = FormulaEvaluator(registry)
    >>> ast = parse("SMA(RSI(14), 10)")
    >>> values = evaluator.compute(ast, candles)
    >>> len(values)  # Series of smoothed RSI values
    86
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from src.application.formula.ast_nodes import (
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.exceptions import FormulaEvaluationError
from src.application.formula.series_indicators import apply_indicator_to_series
from src.application.formula.series_ops import apply_binary_op


class SeriesProvider(Protocol):
    """Protocol for providing series data to the evaluator.

    This protocol allows the evaluator to be decoupled from the
    specific implementation of the indicator registry.
    """

    def get_series(self, name: str) -> list[Decimal]:
        """Get a series by name (price field or indicator).

        Args:
            name: Series name (OPEN, HIGH, LOW, CLOSE, VOLUME, or indicator name)

        Returns:
            Index-aligned list of Decimal values.
        """
        ...

    def compute_indicator(
        self,
        name: str,
        period: int,
    ) -> list[Decimal]:
        """Compute an indicator with the given period.

        Args:
            name: Indicator name (SMA, RSI, EMA, etc.)
            period: Calculation period.

        Returns:
            Index-aligned list of Decimal values.
        """
        ...

    def get_default_period(self, name: str) -> int:
        """Get the default period for an indicator.

        Args:
            name: Indicator name.

        Returns:
            Default period value.
        """
        ...


class FormulaEvaluator:
    """Evaluates formula ASTs to produce series values.

    This class walks the AST and computes values for each node,
    delegating to the series provider for indicator computation.

    Attributes:
        provider: The series provider (typically wraps IndicatorRegistry).
        candle_count: Number of candles being analyzed.

    Example:
        evaluator = FormulaEvaluator(provider)
        values = evaluator.compute(ast, candle_count=100)
    """

    def __init__(self, provider: SeriesProvider) -> None:
        """Initialize the evaluator.

        Args:
            provider: Provider for series data and indicator computation.
        """
        self._provider = provider
        self._candle_count = 0

    def compute(self, ast: ASTNode, candle_count: int) -> list[Decimal]:
        """Evaluate a formula AST.

        Args:
            ast: The AST node to evaluate.
            candle_count: Total number of candles (for context).

        Returns:
            Index-aligned list of Decimal values. The result is aligned
            to the end of the candle series.

        Raises:
            FormulaEvaluationError: If evaluation fails.
        """
        self._candle_count = candle_count
        try:
            return self._evaluate(ast)
        except FormulaEvaluationError:
            raise
        except Exception as e:
            raise FormulaEvaluationError(
                f"Error evaluating formula: {e}",
                node_type=type(ast).__name__,
            ) from e

    def _evaluate(self, node: ASTNode) -> list[Decimal]:
        """Recursively evaluate an AST node.

        Args:
            node: The AST node to evaluate.

        Returns:
            List of Decimal values.
        """
        if isinstance(node, NumberNode):
            return self._evaluate_number(node)
        elif isinstance(node, SeriesNode):
            return self._evaluate_series(node)
        elif isinstance(node, FunctionCallNode):
            return self._evaluate_function(node)
        elif isinstance(node, BinaryOpNode):
            return self._evaluate_binary_op(node)
        else:
            raise FormulaEvaluationError(
                f"Unknown node type: {type(node).__name__}",
                node_type=type(node).__name__,
            )

    def _evaluate_number(self, node: NumberNode) -> list[Decimal]:
        """Evaluate a number node.

        Numbers are represented as single-element lists. When combined
        with series in binary operations, they are broadcast appropriately.

        Args:
            node: The number node.

        Returns:
            Single-element list containing the number.
        """
        # Return single-element list; binary ops will broadcast
        return [node.value]

    def _evaluate_series(self, node: SeriesNode) -> list[Decimal]:
        """Evaluate a series node (price/volume data).

        Args:
            node: The series node.

        Returns:
            List of Decimal values for the series.
        """
        return self._provider.get_series(node.field.upper())

    def _evaluate_function(self, node: FunctionCallNode) -> list[Decimal]:
        """Evaluate a function call node.

        Handles two cases:
        1. Single numeric argument: Indicator with default series (e.g., RSI(14))
        2. Series + numeric argument: Indicator applied to series (e.g., SMA(CLOSE, 20))
        3. Series + series: Apply indicator to computed series (e.g., SMA(RSI(14), 10))

        Args:
            node: The function call node.

        Returns:
            List of Decimal values from the indicator.
        """
        name = node.name.upper()
        args = node.arguments

        # No arguments: indicator with default period
        if len(args) == 0:
            period = self._provider.get_default_period(name)
            return self._provider.compute_indicator(name, period)

        # Single argument: could be period or series
        if len(args) == 1:
            arg = args[0]

            # Single number: period for indicator (e.g., RSI(14))
            if isinstance(arg, NumberNode):
                period = int(arg.value)
                return self._provider.compute_indicator(name, period)

            # Single non-number: series input (e.g., SMA(other_indicator))
            # Use default period
            series = self._evaluate(arg)
            period = self._provider.get_default_period(name)
            return apply_indicator_to_series(name, series, period)

        # Two arguments: series and period (e.g., SMA(CLOSE, 20), SMA(RSI(14), 10))
        if len(args) == 2:
            series_arg, period_arg = args

            # Second argument must be a number (period)
            if not isinstance(period_arg, NumberNode):
                raise FormulaEvaluationError(
                    f"Second argument to {name} must be a number (period)",
                    formula_name=name,
                )

            period = int(period_arg.value)
            series = self._evaluate(series_arg)

            return apply_indicator_to_series(name, series, period)

        raise FormulaEvaluationError(
            f"Too many arguments to {name}: expected 0-2, got {len(args)}",
            formula_name=name,
        )

    def _evaluate_binary_op(self, node: BinaryOpNode) -> list[Decimal]:
        """Evaluate a binary operation.

        Handles +, -, *, / operations between series and/or scalars.
        Result length is the minimum of operand lengths (aligned from end).

        Args:
            node: The binary operation node.

        Returns:
            List of Decimal values.
        """
        left = self._evaluate(node.left)
        right = self._evaluate(node.right)

        return apply_binary_op(node.operator, left, right)


# Temporary compatibility re-export - canonical import is registry_series_provider.py
from src.application.formula.registry_series_provider import (  # noqa: E402, F401
    RegistrySeriesProvider,
)
