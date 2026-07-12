from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import Operator, Outcome
from src.domain.value_objects.risk_signal import RiskLevel
from tests.application.rules.interpreter_fixtures import (
    make_rule,
    make_rule_set,
    make_snapshot,
)


class TestPriorityOrdering:
    """Test that rules are evaluated in priority order."""

    def test_lower_priority_evaluated_first(self):
        """Lower priority number should be evaluated first."""
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
        assert "first" in str(rationale)
        assert "second" not in str(rationale)


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


class TestInterpreterProperties:
    """Test interpreter properties."""

    def test_rule_set_name(self):
        """Should return the rule set name."""
        rule_set = make_rule_set([make_rule("test")], name="my_custom_rules")
        interpreter = YamlRuleInterpreter(rule_set)

        assert interpreter.rule_set_name == "my_custom_rules"

    def test_rule_count(self):
        """Should return the number of rules."""
        rules = [make_rule("r1"), make_rule("r2"), make_rule("r3")]
        rule_set = make_rule_set(rules)
        interpreter = YamlRuleInterpreter(rule_set)

        assert interpreter.rule_count == 3
