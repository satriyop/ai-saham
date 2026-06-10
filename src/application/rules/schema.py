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

from src.domain.value_objects.risk_signal import RiskLevel
from src.domain.value_objects.trade_action import TradeAction


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
    """Definition of a named indicator instance.

    Supports two modes:
    1. Type-based: Standard indicator with type and period (e.g., EMA with period 9)
    2. Formula-based: Composite indicator defined by formula expression

    Example (type-based):
        IndicatorDefinition(name="fast_ema", indicator_type=IndicatorType.EMA, period=9)
        IndicatorDefinition(name="atr_14", indicator_type="ATR", period=14)  # Plugin

    Example (formula-based):
        IndicatorDefinition(name="smooth_rsi", formula="SMA(RSI(14), 10)")
        IndicatorDefinition(name="macd_line", formula="EMA(CLOSE, 12) - EMA(CLOSE, 26)")

    Attributes:
        name: Unique name for this indicator instance (e.g., "fast_ema")
        indicator_type: Type of indicator calculation. Can be:
            - IndicatorType enum for built-ins (RSI, SMA, EMA)
            - str for plugin indicators (e.g., "ATR", "VWAP")
            - None for formula-based indicators
        period: Lookback period for the calculation (>= 1), None for formulas
        formula: Formula expression string (e.g., "SMA(RSI(14), 10)"), None for type-based
        override: If True, allows shadowing built-in indicator names
    """

    name: str
    indicator_type: Union[IndicatorType, str, None] = None
    period: int | None = None
    formula: str | None = None
    override: bool = False

    def __post_init__(self) -> None:
        """Validate indicator definition fields."""
        if not self.name:
            raise ValueError("Indicator name cannot be empty")

        has_type = self.indicator_type is not None
        has_formula = self.formula is not None

        # Must have exactly one: (type + period) OR formula
        if has_type and has_formula:
            raise ValueError(
                f"Indicator '{self.name}' cannot have both 'type' and 'formula'. "
                "Use either type+period OR formula."
            )

        if not has_type and not has_formula:
            raise ValueError(
                f"Indicator '{self.name}' must have either 'type' (with period) "
                "or 'formula'."
            )

        # Type-based validation
        if has_type:
            if self.period is None:
                raise ValueError(
                    f"Indicator '{self.name}' with type requires a period."
                )
            if self.period < 1:
                raise ValueError(
                    f"Indicator period must be >= 1, got {self.period}"
                )

        # Formula-based validation
        if has_formula:
            if self.period is not None:
                raise ValueError(
                    f"Formula indicator '{self.name}' should not have a period. "
                    "Period is determined by the formula expression."
                )
            if not self.formula.strip():
                raise ValueError(
                    f"Indicator '{self.name}' has empty formula."
                )

    def is_formula(self) -> bool:
        """Check if this is a formula-based indicator.

        Returns:
            True if indicator is defined by a formula expression.
        """
        return self.formula is not None

    def get_type_name(self) -> str:
        """Get indicator type as string (works for both enum and plugin types).

        Returns:
            Uppercase type name (e.g., "RSI", "ATR") or "FORMULA" for formulas.
        """
        if self.is_formula():
            return "FORMULA"
        if isinstance(self.indicator_type, IndicatorType):
            return self.indicator_type.value
        return str(self.indicator_type).upper()


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
class SignalMapping:
    """Maps rule outcomes (RiskLevel) to trade actions.

    Used by backtesting to convert rule evaluation results into
    actionable trade signals. Defaults are quant-standard:
    - LOW_RISK -> ENTER_LONG (opportunity to buy)
    - MODERATE -> HOLD (maintain position)
    - HIGH_RISK -> EXIT_LONG (close position)

    Example YAML:
        signal_mapping:
          LOW_RISK: ENTER_LONG
          MODERATE: HOLD
          HIGH_RISK: EXIT_LONG

    Attributes:
        low_risk: Action for LOW_RISK outcome
        moderate: Action for MODERATE outcome
        high_risk: Action for HIGH_RISK outcome
    """

    low_risk: TradeAction = TradeAction.ENTER_LONG
    moderate: TradeAction = TradeAction.HOLD
    high_risk: TradeAction = TradeAction.EXIT_LONG

    def get_action(self, risk_level: RiskLevel) -> TradeAction:
        """Get trade action for a given risk level.

        Args:
            risk_level: Domain RiskLevel from rule evaluation

        Returns:
            Corresponding TradeAction

        Raises:
            ValueError: If risk_level is not recognized
        """
        mapping = {
            RiskLevel.LOW_RISK: self.low_risk,
            RiskLevel.MODERATE: self.moderate,
            RiskLevel.HIGH_RISK: self.high_risk,
        }
        if risk_level not in mapping:
            raise ValueError(f"Unknown risk level: {risk_level}")
        return mapping[risk_level]


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
        signal_mapping: Optional mapping of outcomes to trade actions (for backtesting)
    """

    version: int
    name: str
    default_outcome: Outcome
    rules: tuple[Rule, ...]
    indicators: tuple[IndicatorDefinition, ...] = ()
    description: str | None = None
    signal_mapping: SignalMapping | None = None

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
            self._collect_condition_refs(rule.condition, refs)
        return refs

    @staticmethod
    def _collect_condition_refs(condition: Condition, refs: set[str]) -> None:
        """Recursively collect indicator references from a condition."""
        if isinstance(condition, ConditionIndicatorVsValue):
            refs.add(condition.indicator_name)
        elif isinstance(condition, ConditionIndicatorVsIndicator):
            refs.add(condition.left.name)
            if isinstance(condition.right, IndicatorRef):
                refs.add(condition.right.name)
        elif isinstance(condition, CompoundCondition):
            for sub in condition.conditions:
                RuleSet._collect_condition_refs(sub, refs)

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
