from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import (
    ConditionIndicatorVsValue,
    IndicatorDefinition,
    IndicatorType,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)
from tests.application.rules.interpreter_fixtures import (
    make_indicator_rule,
    make_rule,
    make_rule_set,
)


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
        assert type_name == "SMOOTH_RSI"
        assert period == 0

    def test_mixed_indicator_sources(self):
        """Should resolve indicators from multiple sources."""
        indicator_def = IndicatorDefinition(
            name="custom_sma",
            indicator_type=IndicatorType.SMA,
            period=50,
        )
        rules = [
            make_rule("r1", indicator_name="RSI", value="30"),
            Rule(
                name="r2",
                condition=ConditionIndicatorVsValue(
                    indicator_name="custom_sma",
                    operator=Operator.GT,
                    value=Decimal("100"),
                ),
                outcome=Outcome.LOW_RISK,
            ),
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
                left="fast_ema",
                right="SMA",
            )
        ]
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
