"""
Custom rules DSL for risk assessment.

This module provides a YAML-based domain-specific language (DSL) for defining
custom risk assessment rules without modifying engine source code.

Layer: Application
"""

from src.application.rules.condition_schema import (
    CompoundCondition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorRef,
    Operator,
)
from src.application.rules.exceptions import (
    RulesError,
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
from src.application.rules.indicator_schema import Indicator
from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.outcome_schema import Outcome
from src.application.rules.rule_schema import Rule, RuleSet

__all__ = [
    # Exceptions
    "RulesError",
    "RulesFileError",
    "RulesSchemaError",
    "RulesValidationError",
    # Schema
    "CompoundCondition",
    "Indicator",
    "IndicatorRef",
    "Operator",
    "Outcome",
    "ConditionIndicatorVsValue",
    "ConditionIndicatorVsIndicator",
    "Rule",
    "RuleSet",
    # Interpreter
    "YamlRuleInterpreter",
]
