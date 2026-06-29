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

    HIGH_RISK = "high_risk"
    MODERATE = "moderate"
    LOW_RISK = "low_risk"

