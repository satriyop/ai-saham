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

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from src.application.formula.ast_nodes import (
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.exceptions import FormulaEvaluationError

if TYPE_CHECKING:
    from datetime import date

    from src.domain.entities.candle import Candle


logger = logging.getLogger(__name__)


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
            return self._apply_indicator_to_series(name, series, period)

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

            return self._apply_indicator_to_series(name, series, period)

        raise FormulaEvaluationError(
            f"Too many arguments to {name}: expected 0-2, got {len(args)}",
            formula_name=name,
        )

    def _apply_indicator_to_series(
        self, name: str, series: list[Decimal], period: int
    ) -> list[Decimal]:
        """Apply an indicator function to a series.

        This is used when the indicator is applied to a computed series
        rather than raw price data (e.g., SMA(RSI(14), 10)).

        The implementation depends on the indicator type:
        - SMA: Simple moving average of the series
        - EMA: Exponential moving average of the series
        - RSI: Not applicable to arbitrary series (raises error)

        Args:
            name: Indicator name.
            series: Input series values.
            period: Calculation period.

        Returns:
            List of Decimal values.
        """
        if not series:
            return []

        if name == "SMA":
            return self._compute_sma_on_series(series, period)
        elif name == "EMA":
            return self._compute_ema_on_series(series, period)
        else:
            # For other indicators, we can't easily apply them to arbitrary series
            # Try using the provider's compute_indicator with the first series value
            raise FormulaEvaluationError(
                f"Indicator {name} cannot be applied to computed series. "
                "Only SMA and EMA support series-to-series computation.",
                formula_name=name,
            )

    def _compute_sma_on_series(self, series: list[Decimal], period: int) -> list[Decimal]:
        """Compute SMA on an arbitrary series.

        Args:
            series: Input values.
            period: SMA period.

        Returns:
            SMA values (length = len(series) - period + 1).
        """
        if len(series) < period:
            return []

        result: list[Decimal] = []
        window_sum = sum(series[:period])
        result.append(window_sum / period)

        for i in range(period, len(series)):
            window_sum = window_sum - series[i - period] + series[i]
            result.append(window_sum / period)

        return result

    def _compute_ema_on_series(self, series: list[Decimal], period: int) -> list[Decimal]:
        """Compute EMA on an arbitrary series.

        Uses standard EMA formula: EMA = price * k + EMA_prev * (1 - k)
        where k = 2 / (period + 1)

        Args:
            series: Input values.
            period: EMA period.

        Returns:
            EMA values (length = len(series) - period + 1).
        """
        if len(series) < period:
            return []

        multiplier = Decimal(2) / (Decimal(period) + 1)
        one_minus_k = Decimal(1) - multiplier

        # Initial SMA as seed
        initial_sma = sum(series[:period]) / period
        result: list[Decimal] = [initial_sma]

        # EMA for remaining values
        for i in range(period, len(series)):
            ema = series[i] * multiplier + result[-1] * one_minus_k
            result.append(ema)

        return result

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

        return self._apply_binary_op(node.operator, left, right)

    def _apply_binary_op(
        self, operator: str, left: list[Decimal], right: list[Decimal]
    ) -> list[Decimal]:
        """Apply a binary operator to two series.

        Series are aligned from the end, so shorter series are matched
        to the end of the longer series.

        Special cases:
        - Scalar (single element) is broadcast to match other series length
        - Division by zero returns Decimal("0") and logs warning

        Args:
            operator: The operator (+, -, *, /).
            left: Left operand series.
            right: Right operand series.

        Returns:
            Result series.
        """
        # Handle scalar broadcasting
        if len(left) == 1 and len(right) > 1:
            left = left * len(right)
        elif len(right) == 1 and len(left) > 1:
            right = right * len(left)

        # Align from end (result length = min of both)
        result_len = min(len(left), len(right))
        if result_len == 0:
            return []

        # Slice from end
        left_aligned = left[-result_len:]
        right_aligned = right[-result_len:]

        result: list[Decimal] = []

        for l_val, r_val in zip(left_aligned, right_aligned):
            if operator == "+":
                result.append(l_val + r_val)
            elif operator == "-":
                result.append(l_val - r_val)
            elif operator == "*":
                result.append(l_val * r_val)
            elif operator == "/":
                if r_val == 0:
                    logger.warning("Division by zero in formula evaluation, using 0")
                    result.append(Decimal("0"))
                else:
                    result.append(l_val / r_val)

        return result


class RegistrySeriesProvider:
    """SeriesProvider implementation wrapping IndicatorRegistry.

    This adapter connects the FormulaEvaluator to the IndicatorRegistry,
    managing candle context and series extraction.

    Usage:
        provider = RegistrySeriesProvider(registry, candles)
        evaluator = FormulaEvaluator(provider)
        values = evaluator.compute(ast, len(candles))
    """

    def __init__(
        self,
        registry: "IndicatorRegistry",  # Forward reference
        candles: list["Candle"],
    ) -> None:
        """Initialize the provider.

        Args:
            registry: The indicator registry.
            candles: Candle data for computation.
        """
        self._registry = registry
        self._candles = candles

    def get_series(self, name: str) -> list[Decimal]:
        """Get a series by name.

        Args:
            name: OPEN, HIGH, LOW, CLOSE, VOLUME, or indicator name.

        Returns:
            List of Decimal values.
        """
        name_upper = name.upper()

        # Price series
        if name_upper == "OPEN":
            return [c.open for c in self._candles]
        elif name_upper == "HIGH":
            return [c.high for c in self._candles]
        elif name_upper == "LOW":
            return [c.low for c in self._candles]
        elif name_upper == "CLOSE":
            return [c.close for c in self._candles]
        elif name_upper == "VOLUME":
            return [Decimal(c.volume) for c in self._candles]

        # Indicator series - compute with default period
        period = self._registry.get_default_period(name_upper)
        result = self._registry.compute(name_upper, self._candles, period)
        return [v for _, v in result]  # Strip dates

    def compute_indicator(self, name: str, period: int) -> list[Decimal]:
        """Compute an indicator with the given period.

        Args:
            name: Indicator name.
            period: Calculation period.

        Returns:
            List of Decimal values.
        """
        result = self._registry.compute(name, self._candles, period)
        return [v for _, v in result]  # Strip dates

    def get_default_period(self, name: str) -> int:
        """Get the default period for an indicator.

        Args:
            name: Indicator name.

        Returns:
            Default period value.
        """
        return self._registry.get_default_period(name)


# Type hint for forward reference resolution
if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
