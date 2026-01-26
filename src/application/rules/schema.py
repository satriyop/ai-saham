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


class IndicatorType(Enum):
    """Supported technical indicator types for parameterized definitions.

    Defines which indicator calculations are supported. Users define
    indicator instances using these types with custom periods.

    Example YAML:
        indicators:
          fast_ema:
            type: EMA      # IndicatorType.EMA
            period: 9
    """

    RSI = "RSI"
    SMA = "SMA"
    EMA = "EMA"

    @classmethod
    def from_string(cls, value: str) -> "IndicatorType":
        """Create IndicatorType from string value.

        Args:
            value: Type name (case-insensitive)

        Returns:
            Matching IndicatorType enum

        Raises:
            ValueError: If value doesn't match any type
        """
        normalized = value.upper().strip()
        for ind_type in cls:
            if ind_type.value == normalized:
                return ind_type
        valid = [t.value for t in cls]
        raise ValueError(f"Unknown indicator type '{value}'. Must be one of: {valid}")


# Built-in indicator names (available without explicit definition)
# These use default periods if referenced without definition
BUILTIN_INDICATORS: dict[str, tuple["IndicatorType", int]] = {
    "RSI": (IndicatorType.RSI, 14),
    "SMA": (IndicatorType.SMA, 20),
    "EMA": (IndicatorType.EMA, 20),
}


# Backward compatibility alias
Indicator = IndicatorType


@dataclass(frozen=True)
class IndicatorDefinition:
    """Definition of a named indicator instance with custom period.

    Allows users to create multiple instances of the same indicator type
    with different periods for use in rules.

    Example:
        IndicatorDefinition(name="fast_ema", indicator_type=IndicatorType.EMA, period=9)

    Attributes:
        name: Unique name for this indicator instance (e.g., "fast_ema")
        indicator_type: Type of indicator calculation (RSI, SMA, EMA)
        period: Lookback period for the calculation (>= 1)
        override: If True, allows shadowing built-in indicator names
    """

    name: str
    indicator_type: IndicatorType
    period: int
    override: bool = False

    def __post_init__(self) -> None:
        """Validate indicator definition fields."""
        if not self.name:
            raise ValueError("Indicator name cannot be empty")
        if self.period < 1:
            raise ValueError(f"Indicator period must be >= 1, got {self.period}")


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
    """

    indicator_name: str
    operator: Operator
    value: Decimal


@dataclass(frozen=True)
class ConditionIndicatorVsIndicator:
    """Condition comparing two indicators.

    Example YAML:
        when:
          left:
            indicator: fast_ema   # Custom defined
          operator: ">"
          right:
            indicator: slow_ema   # Custom defined
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

    Contains metadata, indicator definitions, and ordered list of rules.
    The default_outcome is used when no rules match.

    Attributes:
        version: Schema version (must be 1 for Phase 1)
        name: Unique name for this rule set
        default_outcome: Outcome when no rules match (REQUIRED)
        rules: Ordered tuple of rules
        indicators: Tuple of custom indicator definitions (optional)
        description: Optional description of the rule set
    """

    version: int
    name: str
    default_outcome: Outcome
    rules: tuple[Rule, ...]
    indicators: tuple[IndicatorDefinition, ...] = ()
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
        rule_names = [r.name for r in self.rules]
        duplicates = [n for n in rule_names if rule_names.count(n) > 1]
        if duplicates:
            raise ValueError(f"Rule names must be unique. Duplicate: '{duplicates[0]}'")

        # Check for duplicate indicator names
        indicator_names = [i.name for i in self.indicators]
        ind_duplicates = [n for n in indicator_names if indicator_names.count(n) > 1]
        if ind_duplicates:
            raise ValueError(f"Indicator names must be unique. Duplicate: '{ind_duplicates[0]}'")

        # Check for built-in shadowing without override flag
        for indicator in self.indicators:
            if indicator.name in BUILTIN_INDICATORS and not indicator.override:
                raise ValueError(
                    f"Indicator name '{indicator.name}' shadows built-in. "
                    f"Add 'override: true' to confirm, or use a different name like "
                    f"'{indicator.name.lower()}_custom'."
                )

    def get_indicator_definition(self, name: str) -> IndicatorDefinition | None:
        """Get indicator definition by name.

        Args:
            name: Indicator name to look up

        Returns:
            IndicatorDefinition if found, None otherwise
        """
        for indicator in self.indicators:
            if indicator.name == name:
                return indicator
        return None

    def get_all_referenced_indicators(self) -> set[str]:
        """Get all indicator names referenced in rules.

        Returns:
            Set of indicator names used in rule conditions
        """
        refs: set[str] = set()
        for rule in self.rules:
            condition = rule.condition
            if isinstance(condition, ConditionIndicatorVsValue):
                refs.add(condition.indicator_name)
            elif isinstance(condition, ConditionIndicatorVsIndicator):
                refs.add(condition.left.name)
                refs.add(condition.right.name)
        return refs

    def is_indicator_defined(self, name: str) -> bool:
        """Check if an indicator name is defined (custom or built-in).

        Args:
            name: Indicator name to check

        Returns:
            True if the indicator is defined or is a built-in
        """
        # Check custom definitions first
        if self.get_indicator_definition(name) is not None:
            return True
        # Check built-ins
        return name in BUILTIN_INDICATORS
