"""
Tests for YamlRuleInterpreter.

Tests cover:
- Indicator vs value conditions
- Indicator vs indicator conditions
- All operators (including !=)
- Priority ordering
- File order for priority ties
- First matching rule wins
- Default outcome on no match
- Determinism
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import (
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

# --- Test Fixtures ---


def make_snapshot(
    rsi: str = "50",
    sma: str = "100",
    ema: str = "100",
    extras: tuple[tuple[str, Decimal], ...] = (),
) -> IndicatorSnapshot:
    """Create a test indicator snapshot."""
    return IndicatorSnapshot(
        date=date.today(),
        rsi=Decimal(rsi),
        sma=Decimal(sma),
        ema=Decimal(ema),
        extras=extras,
    )


def make_rule(
    name: str,
    indicator_name: str = "RSI",
    operator: Operator = Operator.LT,
    value: str = "30",
    outcome: Outcome = Outcome.LOW_RISK,
    priority: int = 100,
    rationale: str | None = None,
) -> Rule:
    """Create a test rule with indicator vs value condition."""
    return Rule(
        name=name,
        condition=ConditionIndicatorVsValue(
            indicator_name=indicator_name,
            operator=operator,
            value=Decimal(value),
        ),
        outcome=outcome,
        priority=priority,
        rationale=rationale,
    )


def make_indicator_rule(
    name: str,
    left: str = "EMA",
    operator: Operator = Operator.GT,
    right: str = "SMA",
    outcome: Outcome = Outcome.LOW_RISK,
    priority: int = 100,
) -> Rule:
    """Create a test rule with indicator vs indicator condition."""
    return Rule(
        name=name,
        condition=ConditionIndicatorVsIndicator(
            left=IndicatorRef(name=left),
            operator=operator,
            right=IndicatorRef(name=right),
        ),
        outcome=outcome,
        priority=priority,
    )


def make_rule_set(
    rules: list[Rule],
    default_outcome: Outcome = Outcome.MODERATE,
    name: str = "test_rules",
) -> RuleSet:
    """Create a test rule set."""
    return RuleSet(
        version=1,
        name=name,
        default_outcome=default_outcome,
        rules=tuple(rules),
    )


# --- Indicator vs Value Tests ---


class TestIndicatorVsValue:
    """Test indicator-vs-value conditions."""

    def test_less_than_match(self):
        """RSI < 30 should match when RSI is 25."""
        rules = [make_rule("oversold", value="30", operator=Operator.LT)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="25")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100
        assert "oversold" in str(rationale)

    def test_less_than_no_match(self):
        """RSI < 30 should NOT match when RSI is 35."""
        rules = [make_rule("oversold", value="30", operator=Operator.LT)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="35")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE  # default
        assert confidence == 0

    def test_less_than_equal_match_on_equal(self):
        """RSI <= 30 should match when RSI is exactly 30."""
        rules = [make_rule("oversold", value="30", operator=Operator.LE)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100

    def test_greater_than_match(self):
        """RSI > 70 should match when RSI is 75."""
        rules = [
            make_rule(
                "overbought",
                value="70",
                operator=Operator.GT,
                outcome=Outcome.HIGH_RISK,
            )
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="75")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 100

    def test_greater_than_equal_match_on_equal(self):
        """RSI >= 70 should match when RSI is exactly 70."""
        rules = [
            make_rule(
                "overbought",
                value="70",
                operator=Operator.GE,
                outcome=Outcome.HIGH_RISK,
            )
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="70")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK

    def test_equal_match(self):
        """RSI == 50 should match when RSI is exactly 50."""
        rules = [
            make_rule(
                "neutral",
                value="50",
                operator=Operator.EQ,
                outcome=Outcome.MODERATE,
            )
        ]
        rule_set = make_rule_set(rules, default_outcome=Outcome.HIGH_RISK)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="50")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 100

    def test_equal_no_match(self):
        """RSI == 50 should NOT match when RSI is 51."""
        rules = [make_rule("neutral", value="50", operator=Operator.EQ)]
        rule_set = make_rule_set(rules, default_outcome=Outcome.HIGH_RISK)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="51")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK  # default
        assert confidence == 0

    def test_not_equal_match(self):
        """RSI != 50 should match when RSI is 30."""
        rules = [make_rule("not_neutral", value="50", operator=Operator.NE)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100

    def test_not_equal_no_match(self):
        """RSI != 50 should NOT match when RSI is 50."""
        rules = [make_rule("not_neutral", value="50", operator=Operator.NE)]
        rule_set = make_rule_set(rules, default_outcome=Outcome.HIGH_RISK)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="50")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK  # default
        assert confidence == 0


# --- Indicator vs Indicator Tests ---


class TestIndicatorVsIndicator:
    """Test indicator-vs-indicator conditions."""

    def test_ema_above_sma(self):
        """EMA > SMA should match when EMA=105, SMA=100."""
        rules = [make_indicator_rule("bullish", left="EMA", right="SMA")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(ema="105", sma="100")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100

    def test_ema_below_sma(self):
        """EMA > SMA should NOT match when EMA=95, SMA=100."""
        rules = [make_indicator_rule("bullish", left="EMA", right="SMA")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(ema="95", sma="100")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE  # default

    def test_ema_less_than_sma(self):
        """EMA < SMA should match when EMA=95, SMA=100."""
        rules = [
            make_indicator_rule(
                "bearish",
                left="EMA",
                operator=Operator.LT,
                right="SMA",
                outcome=Outcome.HIGH_RISK,
            )
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(ema="95", sma="100")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 100


# --- Priority Ordering Tests ---


class TestPriorityOrdering:
    """Test that rules are evaluated in priority order."""

    def test_lower_priority_evaluated_first(self):
        """Lower priority number should be evaluated first."""
        # Rule A: priority=20, RSI < 40 -> HIGH_RISK
        # Rule B: priority=10, RSI < 50 -> LOW_RISK
        # With RSI=30, both match, but B wins (priority 10 < 20)
        rules = [
            make_rule(
                "rule_a",
                value="40",
                outcome=Outcome.HIGH_RISK,
                priority=20,
            ),
            make_rule(
                "rule_b",
                value="50",
                outcome=Outcome.LOW_RISK,
                priority=10,
            ),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert "rule_b" in str(rationale)

    def test_file_order_on_priority_tie(self):
        """Rules with same priority should be evaluated in file order."""
        # Both rules have priority=100 (default)
        # Rule A appears first in file -> matches first
        rules = [
            make_rule("rule_a", value="50", outcome=Outcome.LOW_RISK),
            make_rule("rule_b", value="50", outcome=Outcome.HIGH_RISK),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert "rule_a" in str(rationale)

    def test_priority_zero_is_highest(self):
        """Priority 0 should be evaluated before all others."""
        rules = [
            make_rule("rule_normal", value="50", outcome=Outcome.MODERATE, priority=100),
            make_rule("rule_highest", value="50", outcome=Outcome.LOW_RISK, priority=0),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert "rule_highest" in str(rationale)


# --- First Matching Rule Wins Tests ---


class TestFirstMatchingRuleWins:
    """Test that the first matching rule wins."""

    def test_stops_on_first_match(self):
        """Should return result from first matching rule only."""
        rules = [
            make_rule("first", value="50", outcome=Outcome.LOW_RISK, priority=1),
            make_rule("second", value="50", outcome=Outcome.HIGH_RISK, priority=2),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        # Only first rule mentioned
        assert "first" in str(rationale)
        assert "second" not in str(rationale)


# --- Default Outcome Tests ---


class TestDefaultOutcome:
    """Test default outcome behavior when no rules match."""

    def test_returns_default_on_no_match(self):
        """Should return default_outcome when no rules match."""
        rules = [make_rule("oversold", value="30")]  # Only matches RSI < 30
        rule_set = make_rule_set(rules, default_outcome=Outcome.HIGH_RISK)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="50")  # Won't match RSI < 30

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 0
        assert "default" in str(rationale).lower()

    def test_default_outcome_low_risk(self):
        """Default outcome can be LOW_RISK."""
        rules = [make_rule("overbought", value="70", operator=Operator.GT)]
        rule_set = make_rule_set(rules, default_outcome=Outcome.LOW_RISK)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="50")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 0

    def test_default_outcome_moderate(self):
        """Default outcome can be MODERATE."""
        rules = [make_rule("overbought", value="70", operator=Operator.GT)]
        rule_set = make_rule_set(rules, default_outcome=Outcome.MODERATE)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="50")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE


# --- Determinism Tests ---


class TestDeterminism:
    """Test that evaluation is deterministic."""

    def test_same_input_same_output(self):
        """Same input should always produce same output."""
        rules = [
            make_rule("rule1", value="40", priority=10),
            make_rule("rule2", value="50", priority=20),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        result1 = interpreter.evaluate(snapshot)
        result2 = interpreter.evaluate(snapshot)
        result3 = interpreter.evaluate(snapshot)

        assert result1 == result2 == result3

    def test_multiple_evaluations_consistent(self):
        """Multiple calls should be consistent."""
        rules = [
            make_rule("a", value="30", priority=10),
            make_rule("b", value="70", operator=Operator.GT, priority=20),
        ]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        results = []
        for _ in range(100):
            snapshot = make_snapshot(rsi="25")
            results.append(interpreter.evaluate(snapshot))

        assert all(r == results[0] for r in results)


# --- Properties Tests ---


class TestInterpreterProperties:
    """Test interpreter properties."""

    def test_profile_name(self):
        """Should return the rule set name."""
        rule_set = make_rule_set([make_rule("test")], name="my_custom_rules")
        interpreter = YamlRuleInterpreter(rule_set)

        assert interpreter.profile_name == "my_custom_rules"

    def test_rule_count(self):
        """Should return the number of rules."""
        rules = [make_rule("r1"), make_rule("r2"), make_rule("r3")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        assert interpreter.rule_count == 3


# --- Rationale Tests ---


class TestRationale:
    """Test rationale generation."""

    def test_includes_rule_name(self):
        """Rationale should include the matched rule name."""
        rules = [make_rule("my_special_rule", value="50")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        _, _, rationale = interpreter.evaluate(snapshot)

        assert "my_special_rule" in str(rationale)

    def test_includes_custom_rationale(self):
        """Should include custom rationale if provided."""
        rules = [make_rule("test", value="50", rationale="Custom explanation here")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        _, _, rationale = interpreter.evaluate(snapshot)

        assert "Custom explanation here" in str(rationale)

    def test_includes_condition_details(self):
        """Should include condition evaluation details."""
        rules = [make_rule("test", value="50", indicator_name="RSI")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        _, _, rationale = interpreter.evaluate(snapshot)

        # Should show the actual values
        rationale_text = str(rationale)
        assert "RSI" in rationale_text
        assert "30" in rationale_text  # actual value


# --- get_required_indicators Tests ---


class TestGetRequiredIndicators:
    """Test get_required_indicators with registry support."""

    def test_builtin_indicators_without_registry(self):
        """Should resolve built-in indicators without registry."""
        rules = [make_rule("test", indicator_name="RSI", value="30")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        required = interpreter.get_required_indicators()

        assert "RSI" in required
        ind_type, period = required["RSI"]
        assert ind_type == IndicatorType.RSI
        assert period == 14  # default

    def test_custom_defined_indicators(self):
        """Should resolve indicators defined in rules file."""
        indicator_def = IndicatorDefinition(
            name="fast_ema",
            indicator_type=IndicatorType.EMA,
            period=9,
        )
        rules = [
            Rule(
                name="test",
                condition=ConditionIndicatorVsValue(
                    indicator_name="fast_ema",
                    operator=Operator.GT,
                    value=Decimal("100"),
                ),
                outcome=Outcome.LOW_RISK,
            )
        ]
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
            indicators=(indicator_def,),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        required = interpreter.get_required_indicators()

        assert "FAST_EMA" in required
        type_name, period = required["FAST_EMA"]
        assert type_name == "EMA"
        assert period == 9

    def test_registry_lookup_for_formula(self):
        """Should resolve formulas from registry."""
        rules = [make_rule("test", indicator_name="SMOOTH_RSI", value="30")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        # Create mock registry
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 0  # Formula
        mock_registry.list_indicators.return_value = ["SMA", "EMA", "RSI", "SMOOTH_RSI"]

        required = interpreter.get_required_indicators(registry=mock_registry)

        assert "SMOOTH_RSI" in required
        type_name, period = required["SMOOTH_RSI"]
        assert type_name == "SMOOTH_RSI"
        assert period == 0  # Formula has period=0

    def test_registry_lookup_for_plugin(self):
        """Should resolve plugins from registry with default period."""
        rules = [make_rule("test", indicator_name="ATR", value="50")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        # Create mock registry
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 14  # ATR default
        mock_registry.list_indicators.return_value = ["SMA", "EMA", "RSI", "ATR"]

        required = interpreter.get_required_indicators(registry=mock_registry)

        assert "ATR" in required
        type_name, period = required["ATR"]
        assert type_name == "ATR"
        assert period == 14

    def test_unknown_indicator_with_registry_raises_error(self):
        """Should raise error for unknown indicator when registry is provided."""
        rules = [make_rule("test", indicator_name="NONEXISTENT", value="30")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        # Create mock registry that doesn't know this indicator
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = False
        mock_registry.list_indicators.return_value = ["SMA", "EMA", "RSI"]

        with pytest.raises(ValueError) as exc_info:
            interpreter.get_required_indicators(registry=mock_registry)

        assert "NONEXISTENT" in str(exc_info.value)
        assert "Unknown indicator" in str(exc_info.value)

    def test_unknown_indicator_without_registry_is_ignored(self):
        """Should silently skip unknown indicators when no registry provided."""
        # This maintains backward compatibility
        rules = [make_rule("test", indicator_name="NONEXISTENT", value="30")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        # No registry provided - should not raise, just skip
        required = interpreter.get_required_indicators()

        # Unknown indicator is skipped
        assert "NONEXISTENT" not in required

    def test_inline_formula_definition_in_rules(self):
        """Should handle inline formula definitions in rules file."""
        indicator_def = IndicatorDefinition(
            name="smooth_rsi",
            formula="SMA(RSI(14), 10)",
        )
        rules = [
            Rule(
                name="test",
                condition=ConditionIndicatorVsValue(
                    indicator_name="smooth_rsi",
                    operator=Operator.LT,
                    value=Decimal("30"),
                ),
                outcome=Outcome.LOW_RISK,
            )
        ]
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
            indicators=(indicator_def,),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        required = interpreter.get_required_indicators()

        assert "SMOOTH_RSI" in required
        type_name, period = required["SMOOTH_RSI"]
        assert type_name == "SMOOTH_RSI"  # Formula uses its own name
        assert period == 0  # Formulas have period=0

    def test_mixed_indicator_sources(self):
        """Should resolve indicators from multiple sources."""
        # Custom definition in rules
        indicator_def = IndicatorDefinition(
            name="custom_sma",
            indicator_type=IndicatorType.SMA,
            period=50,
        )
        rules = [
            # Uses built-in RSI
            make_rule("r1", indicator_name="RSI", value="30"),
            # Uses custom definition
            Rule(
                name="r2",
                condition=ConditionIndicatorVsValue(
                    indicator_name="custom_sma",
                    operator=Operator.GT,
                    value=Decimal("100"),
                ),
                outcome=Outcome.LOW_RISK,
            ),
            # Uses formula from registry
            make_rule("r3", indicator_name="SMOOTH_RSI", value="40"),
        ]
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
            indicators=(indicator_def,),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        # Create mock registry for SMOOTH_RSI
        mock_registry = MagicMock()
        mock_registry.is_registered.side_effect = lambda n: n == "SMOOTH_RSI"
        mock_registry.get_default_period.return_value = 0
        mock_registry.list_indicators.return_value = ["SMOOTH_RSI"]

        required = interpreter.get_required_indicators(registry=mock_registry)

        # Built-in
        assert "RSI" in required
        assert required["RSI"][0] == IndicatorType.RSI
        assert required["RSI"][1] == 14

        # Custom definition
        assert "CUSTOM_SMA" in required
        assert required["CUSTOM_SMA"][0] == "SMA"
        assert required["CUSTOM_SMA"][1] == 50

        # Formula from registry
        assert "SMOOTH_RSI" in required
        assert required["SMOOTH_RSI"][0] == "SMOOTH_RSI"
        assert required["SMOOTH_RSI"][1] == 0

    def test_indicator_vs_indicator_condition_resolves_both(self):
        """Should resolve indicators from both sides of comparison."""
        rules = [
            make_indicator_rule(
                "test",
                left="fast_ema",  # Will be resolved from registry
                right="SMA",  # Built-in
            )
        ]
        # Define fast_ema
        indicator_def = IndicatorDefinition(
            name="fast_ema",
            indicator_type=IndicatorType.EMA,
            period=9,
        )
        rule_set = RuleSet(
            version=1,
            name="test",
            default_outcome=Outcome.MODERATE,
            rules=tuple(rules),
            indicators=(indicator_def,),
        )
        interpreter = YamlRuleInterpreter(rule_set)

        required = interpreter.get_required_indicators()

        assert "FAST_EMA" in required
        assert "SMA" in required
