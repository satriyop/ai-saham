"""
YAML rule interpreter for custom risk assessment.

Evaluates rule sets against indicator snapshots to produce risk levels.
Rules are evaluated in priority order; first matching rule wins.

Layer: Application
"""

from decimal import Decimal
from typing import Callable

from src.application.rules.schema import (
    Condition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    Indicator,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


class YamlRuleInterpreter:
    """Interprets and evaluates YAML-based custom rules.

    Provides deterministic evaluation of rule sets against indicator snapshots.
    Rules are sorted by priority (lower first) and evaluated in order.
    First matching rule wins; default_outcome is used when no rules match.

    This interpreter is stateless and thread-safe.
    """

    # Mapping from Outcome enum to RiskLevel enum
    _OUTCOME_TO_RISK_LEVEL: dict[Outcome, RiskLevel] = {
        Outcome.HIGH_RISK: RiskLevel.HIGH_RISK,
        Outcome.MODERATE: RiskLevel.MODERATE,
        Outcome.LOW_RISK: RiskLevel.LOW_RISK,
    }

    # Mapping from Operator enum to comparison functions
    _OPERATOR_FUNCS: dict[Operator, Callable[[Decimal, Decimal], bool]] = {
        Operator.LT: lambda a, b: a < b,
        Operator.LE: lambda a, b: a <= b,
        Operator.GT: lambda a, b: a > b,
        Operator.GE: lambda a, b: a >= b,
        Operator.EQ: lambda a, b: a == b,
        Operator.NE: lambda a, b: a != b,
    }

    def __init__(self, rule_set: RuleSet) -> None:
        """Initialize the interpreter with a rule set.

        Args:
            rule_set: The RuleSet to evaluate against
        """
        self._rule_set = rule_set
        # Sort rules by priority (lower first). Python's sort is stable,
        # so rules with same priority preserve their file order.
        self._sorted_rules = sorted(rule_set.rules, key=lambda r: r.priority)

    @property
    def profile_name(self) -> str:
        """Return the name of the rule set (used as profile name)."""
        return self._rule_set.name

    @property
    def description(self) -> str | None:
        """Return the rule set description."""
        return self._rule_set.description

    @property
    def rule_count(self) -> int:
        """Return the number of rules in the rule set."""
        return len(self._rule_set.rules)

    def evaluate(
        self, snapshot: IndicatorSnapshot
    ) -> tuple[RiskLevel, int, list[str]]:
        """Evaluate the rule set against an indicator snapshot.

        Returns the same signature as BaseRule.evaluate() for compatibility
        with the existing rule engine infrastructure.

        Rules are evaluated in priority order (lower priority number = first).
        First matching rule wins. If no rules match, default_outcome is used.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values

        Returns:
            Tuple of:
                - RiskLevel: HIGH_RISK, MODERATE, or LOW_RISK
                - confidence: 100 if a rule matched, 0 if using default
                - rationale: List of explanations
        """
        for rule in self._sorted_rules:
            if self._evaluate_condition(rule.condition, snapshot):
                return self._build_match_result(rule, snapshot)

        return self._build_default_result(snapshot)

    def _evaluate_condition(
        self, condition: Condition, snapshot: IndicatorSnapshot
    ) -> bool:
        """Evaluate a single condition against a snapshot.

        Args:
            condition: The condition to evaluate
            snapshot: The indicator snapshot

        Returns:
            True if condition is satisfied, False otherwise
        """
        if isinstance(condition, ConditionIndicatorVsValue):
            return self._evaluate_indicator_vs_value(condition, snapshot)
        elif isinstance(condition, ConditionIndicatorVsIndicator):
            return self._evaluate_indicator_vs_indicator(condition, snapshot)
        else:
            # Should never happen with proper typing
            raise TypeError(f"Unknown condition type: {type(condition)}")

    def _evaluate_indicator_vs_value(
        self, condition: ConditionIndicatorVsValue, snapshot: IndicatorSnapshot
    ) -> bool:
        """Evaluate an indicator-vs-value condition.

        Example: RSI < 30
        """
        indicator_value = self._get_indicator_value(condition.indicator, snapshot)
        compare_func = self._OPERATOR_FUNCS[condition.operator]
        return compare_func(indicator_value, condition.value)

    def _evaluate_indicator_vs_indicator(
        self, condition: ConditionIndicatorVsIndicator, snapshot: IndicatorSnapshot
    ) -> bool:
        """Evaluate an indicator-vs-indicator condition.

        Example: EMA > SMA
        """
        left_value = self._get_indicator_value(condition.left.indicator, snapshot)
        right_value = self._get_indicator_value(condition.right.indicator, snapshot)
        compare_func = self._OPERATOR_FUNCS[condition.operator]
        return compare_func(left_value, right_value)

    def _get_indicator_value(
        self, indicator: Indicator, snapshot: IndicatorSnapshot
    ) -> Decimal:
        """Get the value of an indicator from a snapshot.

        Args:
            indicator: The indicator to get
            snapshot: The indicator snapshot

        Returns:
            The indicator value as Decimal
        """
        if indicator == Indicator.RSI:
            return snapshot.rsi
        elif indicator == Indicator.SMA:
            return snapshot.sma
        elif indicator == Indicator.EMA:
            return snapshot.ema
        else:
            # Should never happen with proper typing
            raise ValueError(f"Unknown indicator: {indicator}")

    def _build_match_result(
        self, rule: Rule, snapshot: IndicatorSnapshot
    ) -> tuple[RiskLevel, int, list[str]]:
        """Build result tuple for a matched rule.

        Args:
            rule: The rule that matched
            snapshot: The indicator snapshot (for context in rationale)

        Returns:
            Tuple of (risk_level, confidence=100, rationale)
        """
        risk_level = self._OUTCOME_TO_RISK_LEVEL[rule.outcome]
        confidence = 100  # Full confidence when rule matches

        rationale = [f"Custom rule '{rule.name}' matched"]
        if rule.rationale:
            rationale.append(rule.rationale)

        # Add condition details
        condition_str = self._format_condition(rule.condition, snapshot)
        rationale.append(f"Condition: {condition_str}")

        return risk_level, confidence, rationale

    def _build_default_result(
        self, snapshot: IndicatorSnapshot
    ) -> tuple[RiskLevel, int, list[str]]:
        """Build result tuple when no rules matched.

        Args:
            snapshot: The indicator snapshot (for context in rationale)

        Returns:
            Tuple of (risk_level, confidence=0, rationale)
        """
        risk_level = self._OUTCOME_TO_RISK_LEVEL[self._rule_set.default_outcome]
        confidence = 0  # No confidence when using default

        rationale = [
            f"No custom rules matched, using default: {self._rule_set.default_outcome.value}",
            f"Evaluated {len(self._rule_set.rules)} rule(s)",
        ]

        return risk_level, confidence, rationale

    def _format_condition(
        self, condition: Condition, snapshot: IndicatorSnapshot
    ) -> str:
        """Format a condition for display in rationale.

        Args:
            condition: The condition to format
            snapshot: The indicator snapshot (for actual values)

        Returns:
            Human-readable condition string
        """
        if isinstance(condition, ConditionIndicatorVsValue):
            actual = self._get_indicator_value(condition.indicator, snapshot)
            return (
                f"{condition.indicator.value}({actual:.2f}) "
                f"{condition.operator.value} {condition.value}"
            )
        elif isinstance(condition, ConditionIndicatorVsIndicator):
            left_actual = self._get_indicator_value(
                condition.left.indicator, snapshot
            )
            right_actual = self._get_indicator_value(
                condition.right.indicator, snapshot
            )
            return (
                f"{condition.left.indicator.value}({left_actual:.2f}) "
                f"{condition.operator.value} "
                f"{condition.right.indicator.value}({right_actual:.2f})"
            )
        else:
            return str(condition)
