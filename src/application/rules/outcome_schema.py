"""
Outcome and signal mapping schema for the custom rules DSL.

Layer: Application
"""

from dataclasses import dataclass
from enum import Enum

from src.domain.value_objects.risk_signal import RiskLevel
from src.domain.value_objects.trade_action import TradeAction


class Outcome(Enum):
    """Possible outcomes from rule evaluation.

    Maps directly to domain RiskLevel values but keeps the DSL
    independent from domain enums.
    """

    HIGH_RISK = "HIGH_RISK"
    MODERATE = "MODERATE"
    LOW_RISK = "LOW_RISK"

    @classmethod
    def from_string(cls, value: str) -> "Outcome":
        """Create Outcome from string value.

        Args:
            value: Outcome name (case-insensitive)

        Returns:
            Matching Outcome enum

        Raises:
            ValueError: If value doesn't match any outcome
        """
        normalized = value.upper().strip()
        for outcome in cls:
            if outcome.value == normalized:
                return outcome
        valid = [o.value for o in cls]
        raise ValueError(f"Unknown outcome '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class SignalMapping:
    """Maps rule outcomes (RiskLevel) to trade actions.

    Used by backtesting to convert rule evaluation results into
    actionable trade signals. Defaults are quant-standard:
    - LOW_RISK -> ENTER_LONG (opportunity to buy)
    - MODERATE -> HOLD (maintain position)
    - HIGH_RISK -> EXIT_LONG (close position)

    Example YAML:
        signal_mapping:
          LOW_RISK: ENTER_LONG
          MODERATE: HOLD
          HIGH_RISK: EXIT_LONG

    Attributes:
        low_risk: Action for LOW_RISK outcome
        moderate: Action for MODERATE outcome
        high_risk: Action for HIGH_RISK outcome
    """

    low_risk: TradeAction = TradeAction.ENTER_LONG
    moderate: TradeAction = TradeAction.HOLD
    high_risk: TradeAction = TradeAction.EXIT_LONG

    def get_action(self, risk_level: RiskLevel) -> TradeAction:
        """Get trade action for a given risk level.

        Args:
            risk_level: Domain RiskLevel from rule evaluation

        Returns:
            Corresponding TradeAction

        Raises:
            ValueError: If risk_level is not recognized
        """
        mapping = {
            RiskLevel.LOW_RISK: self.low_risk,
            RiskLevel.MODERATE: self.moderate,
            RiskLevel.HIGH_RISK: self.high_risk,
        }
        if risk_level not in mapping:
            raise ValueError(f"Unknown risk level: {risk_level}")
        return mapping[risk_level]
