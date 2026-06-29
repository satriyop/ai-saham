"""Risk signal value objects.

Layer: Domain
"""

from enum import Enum


class RiskLevel(Enum):
    """
    Risk level assessment from rule evaluation.

    Represents the outcome of applying rules to indicator snapshots.
    Uses risk-focused terminology to avoid implicit trading advice.
    """

    HIGH_RISK = "HIGH_RISK"
    MODERATE = "MODERATE"
    LOW_RISK = "LOW_RISK"

    @classmethod
    def parse(cls, value: str) -> "RiskLevel":
        """Parse canonical uppercase and legacy lowercase risk values."""
        normalized = value.strip().upper().replace("-", "_")
        for level in cls:
            if normalized in {level.name, level.value}:
                return level
        valid = [level.value for level in cls]
        raise ValueError(f"Invalid risk level '{value}'. Must be one of: {valid}")
