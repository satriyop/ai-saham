"""
Condition schema types for the custom rules DSL.

Layer: Application
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Union


class Operator(Enum):
    """Comparison operators for rule conditions.

    Supports standard comparison operators. No arithmetic operations
    are supported in Phase 1 (no user-defined math).
    """

    LT = "<"  # Less than
    LE = "<="  # Less than or equal
    GT = ">"  # Greater than
    GE = ">="  # Greater than or equal
    EQ = "=="  # Equal
    NE = "!="  # Not equal

    @classmethod
    def from_string(cls, value: str) -> "Operator":
        """Create Operator from string value.

        Args:
            value: Operator symbol (exact match)

        Returns:
            Matching Operator enum

        Raises:
            ValueError: If value doesn't match any operator
        """
        normalized = value.strip()
        for op in cls:
            if op.value == normalized:
                return op
        valid = [o.value for o in cls]
        raise ValueError(f"Unknown operator '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class IndicatorRef:
    """Reference to an indicator for use in conditions.

    Used in indicator-vs-indicator comparisons where both sides
    are indicator values rather than literal values.

    The name can be:
    - A custom defined indicator: "fast_ema", "slow_ema"
    - A built-in indicator: "RSI", "SMA", "EMA"
    """

    name: str


@dataclass(frozen=True)
class ConditionIndicatorVsValue:
    """Condition comparing an indicator to a literal value.

    Example YAML:
        when:
          indicator: rsi_short  # Custom defined indicator
          operator: "<"
          value: 30

        when:
          indicator: RSI        # Built-in indicator
          operator: "<"
          value: 30

        when:
          indicator: SENTIMENT_CATALYST
          operator: "=="
          value: "EARNINGS"
    """

    indicator_name: str
    operator: Operator
    value: Union[Decimal, str]


@dataclass(frozen=True)
class ConditionIndicatorVsIndicator:
    """Condition comparing two indicators, or an indicator to a literal value.

    Supports two forms for the right-hand side:
    1. Indicator reference: right: {indicator: "slow_ema"}
    2. Literal value: right: {value: 50000000000}

    Example YAML:
        when:
          left:
            indicator: fast_ema   # Custom defined
          operator: ">"
          right:
            indicator: slow_ema   # Custom defined

        when:
          left:
            indicator: foreign_flow_3d
          operator: ">"
          right:
            value: 50000000000    # Literal value
    """

    left: IndicatorRef
    operator: Operator
    right: Union[IndicatorRef, Decimal]


@dataclass(frozen=True)
class CompoundCondition:
    """Compound condition combining multiple sub-conditions with AND logic.

    All sub-conditions must be true for the compound condition to be true.

    Example YAML:
        when:
          all:
            - indicator: rsi
              operator: "<"
              value: 30
            - left:
                indicator: CLOSE
              operator: ">"
              right:
                indicator: sma_50
    """

    conditions: tuple[Union["ConditionIndicatorVsValue", "ConditionIndicatorVsIndicator"], ...]


# Union type for all condition types
Condition = Union[
    ConditionIndicatorVsValue,
    ConditionIndicatorVsIndicator,
    CompoundCondition,
]
