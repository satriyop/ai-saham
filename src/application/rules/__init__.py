"""
Custom rules DSL for risk assessment.

This module provides a YAML-based domain-specific language (DSL) for defining
custom risk assessment rules without modifying engine source code.

Layer: Application
"""

from src.application.rules.exceptions import (
    RulesError,
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
)
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

__all__ = [
    # Exceptions
    "RulesError",
    "RulesFileError",
    "RulesSchemaError",
    "RulesValidationError",
    # Schema
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
