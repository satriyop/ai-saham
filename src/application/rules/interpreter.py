"""
YAML rule interpreter for custom risk assessment.

Evaluates rule sets against indicator snapshots to produce risk levels.
Rules are evaluated in priority order; first matching rule wins.

Layer: Application
"""

from decimal import Decimal
from typing import Callable, Union

from typing import TYPE_CHECKING

from src.application.rules.schema import (
    BUILTIN_INDICATORS,
    CompoundCondition,
    Condition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorDefinition,
    IndicatorRef,
    IndicatorType,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry


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
        if isinstance(condition, CompoundCondition):
            return all(
                self._evaluate_condition(sub, snapshot)
                for sub in condition.conditions
            )
        elif isinstance(condition, ConditionIndicatorVsValue):
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

        Example: RSI < 30 (built-in)
        Example: rsi_short < 25 (custom defined)
        """
        indicator_value = self._get_indicator_value(condition.indicator_name, snapshot)
        compare_func = self._OPERATOR_FUNCS[condition.operator]
        
        # If comparing mixed types (e.g. str vs Decimal), try casting or use strict equality
        if type(indicator_value) != type(condition.value):
            if condition.operator in (Operator.EQ, Operator.NE):
                # For EQ/NE, str vs Decimal is safe to compare as strings
                return compare_func(str(indicator_value), str(condition.value))
            else:
                # Ordering operators (<, >) between mixed types are invalid
                return False

        return compare_func(indicator_value, condition.value)

    def _evaluate_indicator_vs_indicator(
        self, condition: ConditionIndicatorVsIndicator, snapshot: IndicatorSnapshot
    ) -> bool:
        """Evaluate an indicator-vs-indicator (or indicator-vs-value) condition.

        Right side can be either an IndicatorRef or a Decimal literal.
        """
        left_value = self._get_indicator_value(condition.left.name, snapshot)
        if isinstance(condition.right, IndicatorRef):
            right_value = self._get_indicator_value(condition.right.name, snapshot)
        else:
            right_value = condition.right
        compare_func = self._OPERATOR_FUNCS[condition.operator]
        return compare_func(left_value, right_value)

    def _get_indicator_value(
        self, indicator_name: str, snapshot: IndicatorSnapshot
    ) -> Decimal:
        """Get the value of an indicator from a snapshot.

        Supports both built-in indicators (RSI, SMA, EMA) and custom
        defined indicators that are stored in snapshot.extras.

        Args:
            indicator_name: The indicator name to look up
            snapshot: The indicator snapshot

        Returns:
            The indicator value as Decimal

        Raises:
            KeyError: If indicator not found in snapshot
        """
        return snapshot.get(indicator_name)

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
        if isinstance(condition, CompoundCondition):
            parts = [
                self._format_condition(sub, snapshot)
                for sub in condition.conditions
            ]
            return " AND ".join(f"({p})" for p in parts)
        elif isinstance(condition, ConditionIndicatorVsValue):
            actual = self._get_indicator_value(condition.indicator_name, snapshot)
            actual_str = f"{actual:.2f}" if isinstance(actual, Decimal) else str(actual)
            return (
                f"{condition.indicator_name}({actual_str}) "
                f"{condition.operator.value} {condition.value}"
            )
        elif isinstance(condition, ConditionIndicatorVsIndicator):
            left_actual = self._get_indicator_value(
                condition.left.name, snapshot
            )
            if isinstance(condition.right, IndicatorRef):
                right_actual = self._get_indicator_value(
                    condition.right.name, snapshot
                )
                right_str = f"{condition.right.name}({right_actual:.2f})"
            else:
                right_str = str(condition.right)
            return (
                f"{condition.left.name}({left_actual:.2f}) "
                f"{condition.operator.value} "
                f"{right_str}"
            )
        else:
            return str(condition)

    def get_required_indicators(
        self,
        registry: "IndicatorRegistry | None" = None,
    ) -> dict[str, tuple[Union[IndicatorType, str], int]]:
        """Get all indicators required to evaluate this rule set.

        Returns a dictionary mapping indicator names to (type, period) tuples.
        Includes custom definitions, built-in defaults, and registered formulas/plugins.

        Args:
            registry: Optional IndicatorRegistry for looking up custom formulas
                     and plugins. If provided, unknown indicators are checked
                     against the registry.

        Returns:
            Dict mapping indicator name to (IndicatorType or str, period).
            Built-in indicators return IndicatorType enum.
            Plugin/formula indicators return uppercase string with period=0 for formulas.

        Raises:
            ValueError: If an indicator is not defined, not built-in, and not
                       registered (when registry is provided).
        """
        required: dict[str, tuple[Union[IndicatorType, str], int]] = {}

        # Get all referenced indicator names
        referenced = self._rule_set.get_all_referenced_indicators()

        # Price fields are not indicators — they're resolved at runtime
        _PRICE_FIELDS = frozenset({"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"})

        for name in referenced:
            name_upper = name.upper()

            # Skip price fields — they are resolved from candle data, not indicators
            if name_upper in _PRICE_FIELDS:
                continue

            # Check if it's a custom definition in the rules file
            definition = self._rule_set.get_indicator_definition(name)
            if definition is not None:
                if definition.is_formula():
                    # Inline formula defined in rules.yaml - use the name, period=0
                    required[name_upper] = (name_upper, 0)
                else:
                    type_name = definition.get_type_name()
                    required[name_upper] = (type_name, definition.period)
            elif name_upper in BUILTIN_INDICATORS:
                # Use built-in default
                required[name_upper] = BUILTIN_INDICATORS[name_upper]
            elif registry is not None and registry.is_registered(name_upper):
                # Registered formula or plugin - use name, registry handles dispatch
                # Period=0 for formulas (embedded), registry.get_default_period() for plugins
                default_period = registry.get_default_period(name_upper)
                required[name_upper] = (name_upper, default_period)
            elif registry is not None:
                # Registry provided but indicator not found - raise error
                raise ValueError(
                    f"Unknown indicator '{name}' in rules. "
                    f"Not defined in rules file, not a built-in, and not registered. "
                    f"Available: {', '.join(sorted(registry.list_indicators()))}"
                )
            # If no registry provided, silently skip (backward compatibility)

        return required
