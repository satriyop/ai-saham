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

import pytest

from src.application.rules.interpreter import YamlRuleInterpreter
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
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel


# --- Test Fixtures ---


def make_snapshot(
    rsi: str = "50",
    sma: str = "100",
    ema: str = "100",
) -> IndicatorSnapshot:
    """Create a test indicator snapshot."""
    return IndicatorSnapshot(
        date=date.today(),
        rsi=Decimal(rsi),
        sma=Decimal(sma),
        ema=Decimal(ema),
    )


def make_rule(
    name: str,
    indicator: Indicator = Indicator.RSI,
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
            indicator=indicator,
            operator=operator,
            value=Decimal(value),
        ),
        outcome=outcome,
        priority=priority,
        rationale=rationale,
    )


def make_indicator_rule(
    name: str,
    left: Indicator = Indicator.EMA,
    operator: Operator = Operator.GT,
    right: Indicator = Indicator.SMA,
    outcome: Outcome = Outcome.LOW_RISK,
    priority: int = 100,
) -> Rule:
    """Create a test rule with indicator vs indicator condition."""
    return Rule(
        name=name,
        condition=ConditionIndicatorVsIndicator(
            left=IndicatorRef(indicator=left),
            operator=operator,
            right=IndicatorRef(indicator=right),
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
        rules = [make_indicator_rule("bullish", left=Indicator.EMA, right=Indicator.SMA)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(ema="105", sma="100")

        risk_level, confidence, rationale = interpreter.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100

    def test_ema_below_sma(self):
        """EMA > SMA should NOT match when EMA=95, SMA=100."""
        rules = [make_indicator_rule("bullish", left=Indicator.EMA, right=Indicator.SMA)]
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
                left=Indicator.EMA,
                operator=Operator.LT,
                right=Indicator.SMA,
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
        rules = [make_rule("test", value="50", indicator=Indicator.RSI)]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)
        snapshot = make_snapshot(rsi="30")

        _, _, rationale = interpreter.evaluate(snapshot)

        # Should show the actual values
        rationale_text = str(rationale)
        assert "RSI" in rationale_text
        assert "30" in rationale_text  # actual value
