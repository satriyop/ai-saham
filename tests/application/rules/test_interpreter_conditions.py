from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import Operator, Outcome
from src.domain.value_objects.risk_signal import RiskLevel
from tests.application.rules.interpreter_fixtures import (
    make_indicator_rule,
    make_rule,
    make_rule_set,
    make_snapshot,
)


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
