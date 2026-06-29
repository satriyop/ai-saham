"""
Trade action value object.

Defines the TradeAction enumeration for backtesting simulation.
Uses quant-standard vocabulary for trade actions.

Layer: Domain
"""

from enum import Enum


class TradeAction(Enum):
    """
    Trade action for backtesting simulation.

    Represents the action to take based on signal evaluation.
    Uses quant-standard terminology for clarity.
    """

    ENTER_LONG = "ENTER_LONG"  # Open long position
    EXIT_LONG = "EXIT_LONG"  # Close long position
    HOLD = "HOLD"  # Maintain current position
    FLAT = "FLAT"  # No position / stay out

    @classmethod
    def from_string(cls, value: str) -> "TradeAction":
        """
        Create TradeAction from string value.

        Args:
            value: Action name (case-insensitive)

        Returns:
            Matching TradeAction enum

        Raises:
            ValueError: If value doesn't match any action
        """
        normalized = value.strip().upper().replace("-", "_")
        for action in cls:
            if normalized in {action.name, action.value}:
                return action
        valid = [a.value for a in cls]
        raise ValueError(f"Invalid action '{value}'. Must be one of: {valid}")
