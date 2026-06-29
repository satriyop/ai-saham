"""
Risk signal value objects.

Defines enumerations for risk levels and signal sensitivities used
throughout the risk assessment domain.

Layer: Domain
"""

from enum import Enum


class RiskLevel(Enum):
    """
    Risk level assessment from rule evaluation.

    Represents the outcome of applying rules to indicator snapshots.
    Uses risk-focused terminology to avoid implicit trading advice.
    """

    HIGH_RISK = "high_risk"
    MODERATE = "moderate"
    LOW_RISK = "low_risk"


class SignalSensitivity(Enum):
    """
    Signal sensitivity preset for rule selection.

    Controls how easily the technical screener triggers — not investor
    risk tolerance. CONSERVATIVE requires both indicators to agree before
    flagging a condition; AGGRESSIVE fires on either indicator alone.

    - CONSERVATIVE: Strictest thresholds, requires indicator agreement
    - BALANCED: Moderate thresholds, majority rules
    - AGGRESSIVE: Widest thresholds, either indicator can signal
    """

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

    @classmethod
    def from_string(cls, value: str) -> "SignalSensitivity":
        """
        Create SignalSensitivity from string value.

        Args:
            value: Sensitivity name (case-insensitive)

        Returns:
            Matching SignalSensitivity enum

        Raises:
            ValueError: If value doesn't match any sensitivity preset
        """
        normalized = value.lower().strip()
        for preset in cls:
            if preset.value == normalized:
                return preset
        valid = [p.value for p in cls]
        raise ValueError(f"Invalid sensitivity '{value}'. Must be one of: {valid}")

