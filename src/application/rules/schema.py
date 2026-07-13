"""
Schema definitions for the custom rules DSL.

Provides immutable dataclasses and enums that represent the structure
of YAML-based rule definitions. All types are frozen for immutability.

Layer: Application

This module is now a compatibility facade. All types are defined in
specialized sub-modules within the same package and re-exported here.
"""

from src.application.rules.condition_schema import (  # noqa: F401
    CompoundCondition,
    Condition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorRef,
    Operator,
)
from src.application.rules.indicator_schema import (  # noqa: F401
    BUILTIN_INDICATORS,
    Indicator,
    IndicatorDefinition,
    IndicatorType,
)
from src.application.rules.outcome_schema import (  # noqa: F401
    Outcome,
    SignalMapping,
)
from src.application.rules.rule_schema import (  # noqa: F401
    Rule,
    RuleSet,
)

__all__ = [
    "IndicatorType",
    "BUILTIN_INDICATORS",
    "Indicator",
    "IndicatorDefinition",
    "Operator",
    "IndicatorRef",
    "ConditionIndicatorVsValue",
    "ConditionIndicatorVsIndicator",
    "CompoundCondition",
    "Condition",
    "Outcome",
    "SignalMapping",
    "Rule",
    "RuleSet",
]
