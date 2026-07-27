"""
signal_mapping section parsing for YAML rule configuration.

Layer: Infrastructure
"""

from typing import Any

from src.application.rules.exceptions import RulesSchemaError, RulesValidationError
from src.application.rules.schema import SignalMapping
from src.domain.value_objects.trade_action import TradeAction


def build_signal_mapping(data: dict[str, Any]) -> SignalMapping:
    """Build SignalMapping from parsed YAML data.

    Parses the optional signal_mapping section that maps risk levels
    to trade actions for backtesting.

    Args:
        data: Dictionary mapping outcome names to action names

    Returns:
        SignalMapping with custom or default actions

    Raises:
        RulesSchemaError: If structure is invalid
        RulesValidationError: If values are invalid
    """
    if not isinstance(data, dict):
        raise RulesSchemaError(f"signal_mapping: expected mapping, got {type(data).__name__}")

    # Map of valid action strings to TradeAction enums
    action_map = {
        "ENTER_LONG": TradeAction.ENTER_LONG,
        "EXIT_LONG": TradeAction.EXIT_LONG,
        "HOLD": TradeAction.HOLD,
        "FLAT": TradeAction.FLAT,
    }

    # Parse each mapping with defaults
    def parse_action(key: str, default: TradeAction) -> TradeAction:
        if key not in data:
            return default
        value = data[key]
        if not isinstance(value, str):
            raise RulesSchemaError(
                f"signal_mapping.{key}: expected string, got {type(value).__name__}"
            )
        normalized = value.upper().strip()
        if normalized not in action_map:
            valid = list(action_map.keys())
            raise RulesValidationError(
                f"signal_mapping.{key}: '{value}' is not valid. Must be one of: {valid}"
            )
        return action_map[normalized]

    return SignalMapping(
        low_risk=parse_action("LOW_RISK", TradeAction.ENTER_LONG),
        moderate=parse_action("MODERATE", TradeAction.HOLD),
        high_risk=parse_action("HIGH_RISK", TradeAction.EXIT_LONG),
    )
