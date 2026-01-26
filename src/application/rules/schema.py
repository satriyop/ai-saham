"""
Schema definitions for the custom rules DSL.

Provides immutable dataclasses and enums that represent the structure
of YAML-based rule definitions. All types are frozen for immutability.

Layer: Application
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Union


class Indicator(Enum):
    """Supported technical indicators for rule conditions.

    Phase 1 supports RSI, SMA, and EMA only. Additional indicators
    can be added in future phases.
    """

    RSI = "RSI"
    SMA = "SMA"
    EMA = "EMA"

    @classmethod
    def from_string(cls, value: str) -> "Indicator":
        """Create Indicator from string value.

        Args:
            value: Indicator name (case-insensitive)

        Returns:
            Matching Indicator enum

        Raises:
            ValueError: If value doesn't match any indicator
        """
        normalized = value.upper().strip()
        for indicator in cls:
            if indicator.value == normalized:
                return indicator
        valid = [i.value for i in cls]
        raise ValueError(f"Unknown indicator '{value}'. Must be one of: {valid}")


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


class Outcome(Enum):
    """Possible outcomes from rule evaluation.

    Maps directly to domain RiskLevel values but keeps the DSL
    independent from domain enums.
    """

    HIGH_RISK = "HIGH_RISK"
    MODERATE = "MODERATE"
    LOW_RISK = "LOW_RISK"

    @classmethod
    def from_string(cls, value: str) -> "Outcome":
        """Create Outcome from string value.

        Args:
            value: Outcome name (case-insensitive)

        Returns:
            Matching Outcome enum

        Raises:
            ValueError: If value doesn't match any outcome
        """
        normalized = value.upper().strip()
        for outcome in cls:
            if outcome.value == normalized:
                return outcome
        valid = [o.value for o in cls]
        raise ValueError(f"Unknown outcome '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class IndicatorRef:
    """Reference to an indicator for use in conditions.

    Used in indicator-vs-indicator comparisons where both sides
    are indicator values rather than literal values.
    """

    indicator: Indicator


@dataclass(frozen=True)
class ConditionIndicatorVsValue:
    """Condition comparing an indicator to a literal value.

    Example YAML:
        when:
          indicator: RSI
          operator: "<"
          value: 30
    """

    indicator: Indicator
    operator: Operator
    value: Decimal


@dataclass(frozen=True)
class ConditionIndicatorVsIndicator:
    """Condition comparing two indicators.

    Example YAML:
        when:
          left:
            indicator: EMA
          operator: ">"
          right:
            indicator: SMA
    """

    left: IndicatorRef
    operator: Operator
    right: IndicatorRef


# Union type for all condition types
Condition = Union[ConditionIndicatorVsValue, ConditionIndicatorVsIndicator]


@dataclass(frozen=True)
class Rule:
    """A single rule in the rule set.

    Rules are evaluated in priority order (lower = first). Rules with
    the same priority are evaluated in file order. First matching rule wins.

    Attributes:
        name: Unique identifier for the rule
        condition: The condition to evaluate
        outcome: The outcome if condition is true
        priority: Evaluation priority (lower = evaluated first, default=100)
        rationale: Optional human-readable explanation
    """

    name: str
    condition: Condition
    outcome: Outcome
    priority: int = 100
    rationale: str | None = None

    def __post_init__(self) -> None:
        """Validate rule fields."""
        if not self.name:
            raise ValueError("Rule name cannot be empty")
        if not isinstance(self.priority, int):
            raise ValueError(f"Rule priority must be an integer, got {type(self.priority)}")


@dataclass(frozen=True)
class RuleSet:
    """Complete set of rules loaded from a YAML file.

    Contains metadata and ordered list of rules. The default_outcome
    is used when no rules match.

    Attributes:
        version: Schema version (must be 1 for Phase 1)
        name: Unique name for this rule set
        default_outcome: Outcome when no rules match (REQUIRED)
        rules: Ordered tuple of rules
        description: Optional description of the rule set
    """

    version: int
    name: str
    default_outcome: Outcome
    rules: tuple[Rule, ...]
    description: str | None = None

    def __post_init__(self) -> None:
        """Validate rule set fields."""
        if self.version != 1:
            raise ValueError(f"Unsupported version {self.version}. Only version 1 is supported.")
        if not self.name:
            raise ValueError("RuleSet name cannot be empty")
        if not self.rules:
            raise ValueError("RuleSet must contain at least one rule")

        # Check for duplicate rule names
        names = [r.name for r in self.rules]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            raise ValueError(f"Rule names must be unique. Duplicate: '{duplicates[0]}'")
