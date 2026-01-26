"""Abstract Syntax Tree (AST) node definitions for formula parsing.

Application layer - Formula AST representation.

This module defines immutable AST nodes used to represent parsed formulas.
All nodes are frozen dataclasses to ensure immutability and enable safe
caching and comparison.

Supported node types:
- NumberNode: Numeric literals (e.g., 14, 20, 0.5)
- SeriesNode: Price/volume series references (OPEN, HIGH, LOW, CLOSE, VOLUME)
- FunctionCallNode: Indicator function calls (e.g., SMA(CLOSE, 20), RSI(14))
- BinaryOpNode: Binary operations (+, -, *, /)

Example:
    Formula: SMA(RSI(14), 10)

    AST:
        FunctionCallNode(
            name="SMA",
            arguments=(
                FunctionCallNode(
                    name="RSI",
                    arguments=(NumberNode(value=Decimal("14")),)
                ),
                NumberNode(value=Decimal("10"))
            )
        )
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class NumberNode:
    """Numeric literal node.

    Represents a constant numeric value in a formula expression.
    Values are stored as Decimal for precision in financial calculations.

    Attributes:
        value: The numeric value as a Decimal.

    Example:
        >>> NumberNode(Decimal("14"))
        NumberNode(value=Decimal('14'))
    """

    value: Decimal

    def __repr__(self) -> str:
        return f"NumberNode(value={self.value!r})"


# Valid series field names (price/volume data)
SERIES_FIELDS = frozenset({"open", "high", "low", "close", "volume"})


@dataclass(frozen=True)
class SeriesNode:
    """Price/volume series reference node.

    Represents a reference to a price or volume data series.
    The field name is normalized to lowercase for consistency.

    Attributes:
        field: The series field name (open, high, low, close, volume).

    Example:
        >>> SeriesNode(field="close")
        SeriesNode(field='close')

    Valid fields: OPEN, HIGH, LOW, CLOSE, VOLUME (case-insensitive)
    """

    field: str

    def __post_init__(self) -> None:
        """Validate and normalize the field name."""
        normalized = self.field.lower()
        if normalized not in SERIES_FIELDS:
            valid = ", ".join(sorted(f.upper() for f in SERIES_FIELDS))
            raise ValueError(f"Invalid series field '{self.field}'. Valid fields: {valid}")
        # Normalize to lowercase (bypass frozen)
        object.__setattr__(self, "field", normalized)

    def __repr__(self) -> str:
        return f"SeriesNode(field={self.field!r})"


@dataclass(frozen=True)
class FunctionCallNode:
    """Function call node for indicator invocations.

    Represents a call to an indicator function with arguments.
    Function names are normalized to uppercase for consistency.

    Attributes:
        name: The function name (e.g., "SMA", "RSI", "EMA").
        arguments: Tuple of argument AST nodes.

    Example:
        >>> FunctionCallNode(
        ...     name="SMA",
        ...     arguments=(SeriesNode("close"), NumberNode(Decimal("20")))
        ... )
        FunctionCallNode(name='SMA', arguments=(...))

    Note:
        Arguments can be any valid ASTNode, allowing nested function calls
        like SMA(RSI(14), 10).
    """

    name: str
    arguments: tuple["ASTNode", ...]

    def __post_init__(self) -> None:
        """Normalize the function name to uppercase."""
        object.__setattr__(self, "name", self.name.upper())

    def __repr__(self) -> str:
        args_str = ", ".join(repr(arg) for arg in self.arguments)
        return f"FunctionCallNode(name={self.name!r}, arguments=({args_str}))"


# Valid binary operators
BINARY_OPERATORS = frozenset({"+", "-", "*", "/"})


@dataclass(frozen=True)
class BinaryOpNode:
    """Binary operation node.

    Represents a binary arithmetic operation between two expressions.

    Attributes:
        operator: The operator string (+, -, *, /).
        left: The left operand AST node.
        right: The right operand AST node.

    Example:
        >>> BinaryOpNode(
        ...     operator="-",
        ...     left=FunctionCallNode("EMA", (SeriesNode("close"), NumberNode(Decimal("12")))),
        ...     right=FunctionCallNode("EMA", (SeriesNode("close"), NumberNode(Decimal("26"))))
        ... )
        BinaryOpNode(operator='-', left=..., right=...)

    Note:
        Operator precedence (* / before + -) is handled by the parser,
        not by this node class.
    """

    operator: str
    left: "ASTNode"
    right: "ASTNode"

    def __post_init__(self) -> None:
        """Validate the operator."""
        if self.operator not in BINARY_OPERATORS:
            valid = ", ".join(sorted(BINARY_OPERATORS))
            raise ValueError(f"Invalid operator '{self.operator}'. Valid operators: {valid}")

    def __repr__(self) -> str:
        return f"BinaryOpNode(operator={self.operator!r}, left={self.left!r}, right={self.right!r})"


# Union type for all AST node types
ASTNode = Union[NumberNode, SeriesNode, FunctionCallNode, BinaryOpNode]
