"""
`when` condition parsing for YAML rule configuration.

Layer: Infrastructure
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from src.application.rules.exceptions import RulesSchemaError, RulesValidationError
from src.application.rules.schema import (
    CompoundCondition,
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorRef,
    Operator,
)
from src.infrastructure.config.rules_parser_helpers import require_field


def build_rule_condition(
    data: dict[str, Any],
) -> ConditionIndicatorVsValue | ConditionIndicatorVsIndicator | CompoundCondition:
    """Build a Condition from parsed YAML data.

    Detects condition type based on fields present:
    - all: list of sub-conditions (CompoundCondition, logical AND)
    - indicator + value: ConditionIndicatorVsValue
    - left + right: ConditionIndicatorVsIndicator

    Args:
        data: Condition dictionary from YAML

    Returns:
        Validated Condition

    Raises:
        RulesSchemaError: If required fields missing or wrong type
        RulesValidationError: If condition content is invalid
    """
    # Check for compound condition (all: [...])
    if "all" in data:
        return _build_compound_condition(data)

    # Check for indicator-vs-value condition
    if "indicator" in data and "value" in data:
        return _build_indicator_vs_value(data)

    # Check for indicator-vs-indicator condition (or indicator-vs-value in left/right form)
    if "left" in data and "right" in data:
        return _build_indicator_vs_indicator(data)

    raise RulesSchemaError(
        "when: must have either (indicator + operator + value), "
        "(left + operator + right), or (all: [...])"
    )


def _build_compound_condition(data: dict[str, Any]) -> CompoundCondition:
    """Build a compound AND condition from a list of sub-conditions.

    Args:
        data: Condition dictionary containing an 'all' key with a list.

    Returns:
        CompoundCondition with all sub-conditions.

    Raises:
        RulesSchemaError: If structure is invalid.
    """
    sub_list = data["all"]
    if not isinstance(sub_list, list):
        raise RulesSchemaError(f"when.all: expected list, got {type(sub_list).__name__}")
    if len(sub_list) < 2:
        raise RulesSchemaError("when.all: must have at least 2 sub-conditions")

    subs = []
    for i, sub_data in enumerate(sub_list):
        if not isinstance(sub_data, dict):
            raise RulesSchemaError(
                f"when.all[{i}]: expected mapping, got {type(sub_data).__name__}"
            )
        try:
            sub = build_rule_condition(sub_data)
            subs.append(sub)
        except (RulesSchemaError, RulesValidationError) as e:
            raise type(e)(f"when.all[{i}]: {e}")

    return CompoundCondition(conditions=tuple(subs))


def _build_indicator_vs_value(
    data: dict[str, Any],
) -> ConditionIndicatorVsValue:
    """Build an indicator-vs-value condition.

    Indicator references are strings that can be either:
    - Custom defined indicators (e.g., "fast_ema", "rsi_short")
    - Built-in indicators ("RSI", "SMA", "EMA")

    Validation of references happens after all indicators are parsed.

    Args:
        data: Condition dictionary

    Returns:
        ConditionIndicatorVsValue

    Raises:
        RulesSchemaError: If fields missing
        RulesValidationError: If content invalid
    """
    require_field(data, "indicator", str, "when")
    require_field(data, "operator", str, "when")
    # value can be int, float, or str

    # Indicator is now a string reference (validated later)
    indicator_name = data["indicator"].strip()
    if not indicator_name:
        raise RulesValidationError("when.indicator: cannot be empty")

    try:
        operator = Operator.from_string(data["operator"])
    except ValueError as e:
        raise RulesValidationError(f"when.operator: {e}")

    try:
        # First try parsing as Decimal
        value = Decimal(str(data["value"]))
    except (InvalidOperation, TypeError):
        # If it fails, keep it as a string
        value = str(data["value"])

    return ConditionIndicatorVsValue(
        indicator_name=indicator_name,
        operator=operator,
        value=value,
    )


def _build_indicator_vs_indicator(
    data: dict[str, Any],
) -> ConditionIndicatorVsIndicator:
    """Build an indicator-vs-indicator (or indicator-vs-value) condition.

    Left side must always be an indicator reference. Right side can be
    either an indicator reference or a literal value:
    - right: {indicator: "slow_ema"}  — indicator vs indicator
    - right: {value: 50000000000}     — indicator vs literal value

    Args:
        data: Condition dictionary

    Returns:
        ConditionIndicatorVsIndicator

    Raises:
        RulesSchemaError: If fields missing
        RulesValidationError: If content invalid
    """
    require_field(data, "left", dict, "when")
    require_field(data, "operator", str, "when")
    require_field(data, "right", dict, "when")

    try:
        operator = Operator.from_string(data["operator"])
    except ValueError as e:
        raise RulesValidationError(f"when.operator: {e}")

    left_data = data["left"]
    right_data = data["right"]

    # Left side must always be an indicator reference
    require_field(left_data, "indicator", str, "when.left")
    left_name = left_data["indicator"].strip()
    if not left_name:
        raise RulesValidationError("when.left.indicator: cannot be empty")

    # Right side: indicator reference OR literal value
    if "indicator" in right_data:
        right_name = right_data["indicator"]
        if not isinstance(right_name, str) or not right_name.strip():
            raise RulesValidationError("when.right.indicator: must be a non-empty string")
        right: IndicatorRef | Decimal = IndicatorRef(name=right_name.strip())
    elif "value" in right_data:
        try:
            right = Decimal(str(right_data["value"]))
        except (InvalidOperation, TypeError):
            raise RulesValidationError(
                f"when.right.value: must be a number, got '{right_data['value']}'"
            )
    else:
        raise RulesSchemaError("when.right: must have either 'indicator' or 'value'")

    return ConditionIndicatorVsIndicator(
        left=IndicatorRef(name=left_name),
        operator=operator,
        right=right,
    )
