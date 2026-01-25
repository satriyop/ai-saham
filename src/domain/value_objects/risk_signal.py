"""
Risk signal value objects.

Defines enumerations for risk levels and risk profiles used
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


class RiskProfile(Enum):
    """
    Risk profile for rule selection.

    Determines which rule thresholds and logic to apply:
    - CONSERVATIVE: Strictest thresholds, requires indicator agreement
    - BALANCED: Moderate thresholds, majority rules
    - AGGRESSIVE: Widest thresholds, either indicator can signal
    """

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

    @classmethod
    def from_string(cls, value: str) -> "RiskProfile":
        """
        Create RiskProfile from string value.

        Args:
            value: Profile name (case-insensitive)

        Returns:
            Matching RiskProfile enum

        Raises:
            ValueError: If value doesn't match any profile
        """
        normalized = value.lower().strip()
        for profile in cls:
            if profile.value == normalized:
                return profile
        valid = [p.value for p in cls]
        raise ValueError(f"Invalid profile '{value}'. Must be one of: {valid}")
