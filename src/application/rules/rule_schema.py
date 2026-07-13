"""
Rule and RuleSet schema for the custom rules DSL.

Layer: Application
"""

from dataclasses import dataclass

from src.application.rules.condition_schema import (
    CompoundCondition,
    Condition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorRef,
)
from src.application.rules.indicator_schema import BUILTIN_INDICATORS, IndicatorDefinition
from src.application.rules.outcome_schema import Outcome, SignalMapping


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
