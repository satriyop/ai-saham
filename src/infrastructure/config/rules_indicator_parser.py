"""
Indicator section parsing and indicator reference validation for YAML rules.

Layer: Infrastructure
"""

from typing import TYPE_CHECKING, Any

from src.application.rules.exceptions import RulesSchemaError, RulesValidationError
from src.application.rules.schema import (
    BUILTIN_INDICATORS,
    IndicatorDefinition,
    IndicatorType,
    RuleSet,
)
from src.infrastructure.config.rules_parser_helpers import require_field

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry


# Price field names that are valid as indicator references in rules
_PRICE_FIELDS = frozenset({"OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"})


def build_rule_indicators(
    indicators_data: dict[str, Any],
) -> tuple[IndicatorDefinition, ...]:
    """Build indicator definitions from parsed YAML data.

    Args:
        indicators_data: Dictionary mapping indicator names to their definitions

    Returns:
        Tuple of IndicatorDefinition objects

    Raises:
        RulesSchemaError: If indicator structure is invalid
        RulesValidationError: If indicator content is invalid
    """
    if not isinstance(indicators_data, dict):
        raise RulesSchemaError(
            f"indicators: expected mapping, got {type(indicators_data).__name__}"
        )

    indicators = []
    for ind_name, ind_data in indicators_data.items():
        try:
            indicator = build_indicator_definition(ind_name, ind_data)
            indicators.append(indicator)
        except (RulesSchemaError, RulesValidationError) as e:
            raise type(e)(f"indicators.{ind_name}: {e}")

    return tuple(indicators)


def build_indicator_definition(name: str, data: dict[str, Any]) -> IndicatorDefinition:
    """Build a single indicator definition.

    Supports three modes:
    1. Built-in indicators (SMA, EMA, RSI) with type and period
    2. Plugin indicators (ATR, VWAP, etc.) with type and period
    3. Formula-based indicators with formula expression

    Args:
        name: Indicator instance name
        data: Indicator definition dictionary

    Returns:
        IndicatorDefinition object

    Raises:
        RulesSchemaError: If required fields missing
        RulesValidationError: If values are invalid
    """
    if not isinstance(data, dict):
        raise RulesSchemaError(f"expected mapping, got {type(data).__name__}")

    has_type = "type" in data
    has_formula = "formula" in data

    # Validate mutual exclusivity
    if has_type and has_formula:
        raise RulesSchemaError(
            "cannot have both 'type' and 'formula'. Use either type+period OR formula."
        )

    if not has_type and not has_formula:
        raise RulesSchemaError("must have either 'type' (with period) or 'formula'")

    # Parse override (common to both modes)
    override = data.get("override", False)
    if not isinstance(override, bool):
        raise RulesSchemaError(f"override: expected bool, got {type(override).__name__}")

    # Formula-based indicator
    if has_formula:
        formula = data["formula"]
        if not isinstance(formula, str):
            raise RulesSchemaError(f"formula: expected string, got {type(formula).__name__}")

        formula = formula.strip()
        if not formula:
            raise RulesValidationError("formula: cannot be empty")

        # Period should not be specified for formula indicators
        if "period" in data:
            raise RulesSchemaError(
                "formula indicators should not have 'period'. "
                "Period is determined by the formula expression."
            )

        try:
            return IndicatorDefinition(
                name=name,
                formula=formula,
                override=override,
            )
        except ValueError as e:
            raise RulesValidationError(str(e))

    # Type-based indicator (existing logic)
    require_field(data, "period", int, "indicator")

    # Parse indicator type - try built-in first, then accept as plugin name
    type_str = data["type"].strip()
    try:
        indicator_type: IndicatorType | str = IndicatorType.from_string(type_str)
    except ValueError:
        # Not a built-in - store as string for plugin lookup
        # Plugin validation happens at runtime via IndicatorRegistry
        indicator_type = type_str.upper()

    period = data["period"]
    if period < 1:
        raise RulesValidationError(f"period: must be >= 1, got {period}")

    try:
        return IndicatorDefinition(
            name=name,
            indicator_type=indicator_type,
            period=period,
            override=override,
        )
    except ValueError as e:
        raise RulesValidationError(str(e))


def validate_indicator_references(
    rule_set: RuleSet,
    registry: "IndicatorRegistry | None" = None,
) -> None:
    """Validate that all indicator references in rules are defined.

    Args:
        rule_set: The rule set to validate
        registry: Optional IndicatorRegistry for checking registered
                 formulas and plugins

    Raises:
        RulesValidationError: If any indicator reference is undefined
    """
    referenced = rule_set.get_all_referenced_indicators()
    for ref_name in referenced:
        # Check if it's a price field (OPEN, HIGH, LOW, CLOSE, VOLUME)
        if ref_name.upper() in _PRICE_FIELDS:
            continue

        # Check if defined in rules file or is a built-in
        if rule_set.is_indicator_defined(ref_name):
            continue

        # Check if registered in the registry (formula or plugin)
        if registry is not None and registry.is_registered(ref_name.upper()):
            continue

        # Not found anywhere - raise error
        sources = list(BUILTIN_INDICATORS.keys()) + sorted(_PRICE_FIELDS)
        if registry is not None:
            # Add registry indicators to the error message
            sources.extend(sorted(registry.list_indicators()))
            sources = sorted(set(sources))

        raise RulesValidationError(
            f"Rule references undefined indicator '{ref_name}'. "
            f"Define it in the 'indicators' section, use a built-in, "
            f"or register a formula. Available: {', '.join(sources[:10])}"
            + ("..." if len(sources) > 10 else "")
        )
