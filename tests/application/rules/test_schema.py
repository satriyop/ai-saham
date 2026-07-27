"""
Tests for custom rules schema definitions.

Tests cover:
- Enum parsing and validation
- Dataclass immutability
- Validation rules (duplicates, empty names, etc.)
- All condition types
"""

from decimal import Decimal

import pytest

from src.application.rules.schema import (
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    Indicator,
    IndicatorRef,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)

# --- Indicator Enum Tests ---


class TestIndicatorEnum:
    """Test Indicator enum behavior."""

    def test_from_string_valid_uppercase(self):
        """Should parse uppercase indicator names."""
        assert Indicator.from_string("RSI") == Indicator.RSI
        assert Indicator.from_string("SMA") == Indicator.SMA
        assert Indicator.from_string("EMA") == Indicator.EMA

    def test_from_string_valid_lowercase(self):
        """Should parse lowercase indicator names (case-insensitive)."""
        assert Indicator.from_string("rsi") == Indicator.RSI
        assert Indicator.from_string("sma") == Indicator.SMA
        assert Indicator.from_string("ema") == Indicator.EMA

    def test_from_string_valid_mixed_case(self):
        """Should parse mixed case indicator names."""
        assert Indicator.from_string("Rsi") == Indicator.RSI
        assert Indicator.from_string("SmA") == Indicator.SMA

    def test_from_string_strips_whitespace(self):
        """Should handle whitespace around indicator names."""
        assert Indicator.from_string("  RSI  ") == Indicator.RSI

    def test_from_string_invalid_raises(self):
        """Should raise ValueError for unknown indicator types."""
        with pytest.raises(ValueError, match="Unknown indicator type 'MACD'"):
            Indicator.from_string("MACD")

    def test_from_string_empty_raises(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="Unknown indicator"):
            Indicator.from_string("")


# --- Operator Enum Tests ---


class TestOperatorEnum:
    """Test Operator enum behavior."""

    def test_from_string_all_operators(self):
        """Should parse all valid operators."""
        assert Operator.from_string("<") == Operator.LT
        assert Operator.from_string("<=") == Operator.LE
        assert Operator.from_string(">") == Operator.GT
        assert Operator.from_string(">=") == Operator.GE
        assert Operator.from_string("==") == Operator.EQ
        assert Operator.from_string("!=") == Operator.NE

    def test_from_string_strips_whitespace(self):
        """Should handle whitespace around operators."""
        assert Operator.from_string("  <  ") == Operator.LT
        assert Operator.from_string(" >= ") == Operator.GE

    def test_from_string_invalid_raises(self):
        """Should raise ValueError for unknown operators."""
        with pytest.raises(ValueError, match="Unknown operator '~'"):
            Operator.from_string("~")

    def test_from_string_similar_invalid_raises(self):
        """Should reject operators that look similar but are invalid."""
        with pytest.raises(ValueError, match="Unknown operator '='"):
            Operator.from_string("=")  # Should be ==

        with pytest.raises(ValueError, match="Unknown operator '<>'"):
            Operator.from_string("<>")  # Should be !=


# --- Outcome Enum Tests ---


class TestOutcomeEnum:
    """Test Outcome enum behavior."""

    def test_from_string_all_outcomes(self):
        """Should parse all valid outcomes."""
        assert Outcome.from_string("HIGH_RISK") == Outcome.HIGH_RISK
        assert Outcome.from_string("MODERATE") == Outcome.MODERATE
        assert Outcome.from_string("LOW_RISK") == Outcome.LOW_RISK

    def test_from_string_case_insensitive(self):
        """Should parse outcomes case-insensitively."""
        assert Outcome.from_string("high_risk") == Outcome.HIGH_RISK
        assert Outcome.from_string("Low_Risk") == Outcome.LOW_RISK
        assert Outcome.from_string("moderate") == Outcome.MODERATE

    def test_from_string_invalid_raises(self):
        """Should raise ValueError for unknown outcomes."""
        with pytest.raises(ValueError, match="Unknown outcome 'BUY'"):
            Outcome.from_string("BUY")


# --- Condition Dataclass Tests ---


class TestConditionIndicatorVsValue:
    """Test ConditionIndicatorVsValue dataclass."""

    def test_creation(self):
        """Should create a valid condition."""
        condition = ConditionIndicatorVsValue(
            indicator_name="RSI",
            operator=Operator.LT,
            value=Decimal("30"),
        )
        assert condition.indicator_name == "RSI"
        assert condition.operator == Operator.LT
        assert condition.value == Decimal("30")

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        condition = ConditionIndicatorVsValue(
            indicator_name="RSI",
            operator=Operator.LT,
            value=Decimal("30"),
        )
        with pytest.raises(AttributeError):
            condition.value = Decimal("40")

    def test_equality(self):
        """Same conditions should be equal."""
        c1 = ConditionIndicatorVsValue(
            indicator_name="RSI",
            operator=Operator.LT,
            value=Decimal("30"),
        )
        c2 = ConditionIndicatorVsValue(
            indicator_name="RSI",
            operator=Operator.LT,
            value=Decimal("30"),
        )
        assert c1 == c2


class TestConditionIndicatorVsIndicator:
    """Test ConditionIndicatorVsIndicator dataclass."""

    def test_creation(self):
        """Should create a valid condition."""
        condition = ConditionIndicatorVsIndicator(
            left=IndicatorRef(name="EMA"),
            operator=Operator.GT,
            right=IndicatorRef(name="SMA"),
        )
        assert condition.left.name == "EMA"
        assert condition.operator == Operator.GT
        assert condition.right.name == "SMA"

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        condition = ConditionIndicatorVsIndicator(
            left=IndicatorRef(name="EMA"),
            operator=Operator.GT,
            right=IndicatorRef(name="SMA"),
        )
        with pytest.raises(AttributeError):
            condition.operator = Operator.LT


# --- Rule Dataclass Tests ---


class TestRule:
    """Test Rule dataclass."""

    def test_creation_minimal(self):
        """Should create a rule with minimal fields."""
        rule = Rule(
            name="test_rule",
            condition=ConditionIndicatorVsValue(
                indicator_name="RSI",
                operator=Operator.LT,
                value=Decimal("30"),
            ),
            outcome=Outcome.LOW_RISK,
        )
        assert rule.name == "test_rule"
        assert rule.priority == 100  # default
        assert rule.rationale is None  # optional

    def test_creation_full(self):
        """Should create a rule with all fields."""
        rule = Rule(
            name="test_rule",
            condition=ConditionIndicatorVsValue(
                indicator_name="RSI",
                operator=Operator.LT,
                value=Decimal("30"),
            ),
            outcome=Outcome.LOW_RISK,
            priority=10,
            rationale="RSI indicates oversold",
        )
        assert rule.priority == 10
        assert rule.rationale == "RSI indicates oversold"

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        rule = Rule(
            name="test_rule",
            condition=ConditionIndicatorVsValue(
                indicator_name="RSI",
                operator=Operator.LT,
                value=Decimal("30"),
            ),
            outcome=Outcome.LOW_RISK,
        )
        with pytest.raises(AttributeError):
            rule.name = "modified"

    def test_empty_name_raises(self):
        """Should raise ValueError for empty name."""
        with pytest.raises(ValueError, match="Rule name cannot be empty"):
            Rule(
                name="",
                condition=ConditionIndicatorVsValue(
                    indicator_name="RSI",
                    operator=Operator.LT,
                    value=Decimal("30"),
                ),
                outcome=Outcome.LOW_RISK,
            )


# --- RuleSet Dataclass Tests ---


class TestRuleSet:
    """Test RuleSet dataclass."""

    def _make_rule(self, name: str, priority: int = 100) -> Rule:
        """Helper to create a test rule."""
        return Rule(
            name=name,
            condition=ConditionIndicatorVsValue(
                indicator_name="RSI",
                operator=Operator.LT,
                value=Decimal("30"),
            ),
            outcome=Outcome.LOW_RISK,
            priority=priority,
        )

    def test_creation_minimal(self):
        """Should create a rule set with required fields."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        assert rule_set.version == 1
        assert rule_set.name == "test_rules"
        assert rule_set.default_outcome == Outcome.MODERATE
        assert len(rule_set.rules) == 1
        assert rule_set.description is None

    def test_creation_with_description(self):
        """Should accept optional description."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
            description="Test rule set",
        )
        assert rule_set.description == "Test rule set"

    def test_immutability(self):
        """Should be immutable (frozen dataclass)."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(self._make_rule("rule1"),),
        )
        with pytest.raises(AttributeError):
            rule_set.name = "modified"

    def test_unsupported_version_raises(self):
        """Should raise ValueError for unsupported version."""
        with pytest.raises(ValueError, match="Unsupported version 2"):
            RuleSet(
                version=2,
                name="test_rules",
                default_outcome=Outcome.MODERATE,
                rules=(self._make_rule("rule1"),),
            )

    def test_empty_name_raises(self):
        """Should raise ValueError for empty name."""
        with pytest.raises(ValueError, match="RuleSet name cannot be empty"):
            RuleSet(
                version=1,
                name="",
                default_outcome=Outcome.MODERATE,
                rules=(self._make_rule("rule1"),),
            )

    def test_empty_rules_raises(self):
        """Should raise ValueError for empty rules."""
        with pytest.raises(ValueError, match="at least one rule"):
            RuleSet(
                version=1,
                name="test_rules",
                default_outcome=Outcome.MODERATE,
                rules=(),
            )

    def test_duplicate_rule_names_raises(self):
        """Should raise ValueError for duplicate rule names."""
        with pytest.raises(ValueError, match="Duplicate: 'duplicate_name'"):
            RuleSet(
                version=1,
                name="test_rules",
                default_outcome=Outcome.MODERATE,
                rules=(
                    self._make_rule("duplicate_name"),
                    self._make_rule("duplicate_name"),
                ),
            )

    def test_multiple_unique_rules_ok(self):
        """Should accept multiple rules with unique names."""
        rule_set = RuleSet(
            version=1,
            name="test_rules",
            default_outcome=Outcome.MODERATE,
            rules=(
                self._make_rule("rule1"),
                self._make_rule("rule2"),
                self._make_rule("rule3"),
            ),
        )
        assert len(rule_set.rules) == 3


class TestFacadeExports:
    """Every public symbol in schema.py re-exports the canonical definition."""

    def test_indicator_type_is_canonical(self):
        from src.application.rules import indicator_schema
        from src.application.rules.schema import IndicatorType

        assert IndicatorType is indicator_schema.IndicatorType

    def test_builtin_indicators_is_canonical(self):
        from src.application.rules import indicator_schema
        from src.application.rules.schema import BUILTIN_INDICATORS

        assert BUILTIN_INDICATORS is indicator_schema.BUILTIN_INDICATORS

    def test_indicator_alias_is_canonical(self):
        from src.application.rules import indicator_schema
        from src.application.rules.schema import Indicator

        assert Indicator is indicator_schema.Indicator

    def test_indicator_definition_is_canonical(self):
        from src.application.rules import indicator_schema
        from src.application.rules.schema import IndicatorDefinition

        assert IndicatorDefinition is indicator_schema.IndicatorDefinition

    def test_operator_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import Operator

        assert Operator is condition_schema.Operator

    def test_indicator_ref_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import IndicatorRef

        assert IndicatorRef is condition_schema.IndicatorRef

    def test_condition_indicator_vs_value_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import ConditionIndicatorVsValue

        assert ConditionIndicatorVsValue is condition_schema.ConditionIndicatorVsValue

    def test_condition_indicator_vs_indicator_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import ConditionIndicatorVsIndicator

        assert ConditionIndicatorVsIndicator is condition_schema.ConditionIndicatorVsIndicator

    def test_compound_condition_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import CompoundCondition

        assert CompoundCondition is condition_schema.CompoundCondition

    def test_condition_union_is_canonical(self):
        from src.application.rules import condition_schema
        from src.application.rules.schema import Condition

        assert Condition is condition_schema.Condition

    def test_outcome_is_canonical(self):
        from src.application.rules import outcome_schema
        from src.application.rules.schema import Outcome

        assert Outcome is outcome_schema.Outcome

    def test_signal_mapping_is_canonical(self):
        from src.application.rules import outcome_schema
        from src.application.rules.schema import SignalMapping

        assert SignalMapping is outcome_schema.SignalMapping

    def test_rule_is_canonical(self):
        from src.application.rules import rule_schema
        from src.application.rules.schema import Rule

        assert Rule is rule_schema.Rule

    def test_rule_set_is_canonical(self):
        from src.application.rules import rule_schema
        from src.application.rules.schema import RuleSet

        assert RuleSet is rule_schema.RuleSet
