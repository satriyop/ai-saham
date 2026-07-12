from src.application.rules.interpreter import YamlRuleInterpreter
from tests.application.rules.interpreter_fixtures import (
    make_rule,
    make_rule_set,
    make_snapshot,
)


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

        rationale_text = str(rationale)
        assert "RSI" in rationale_text
        assert "30" in rationale_text
