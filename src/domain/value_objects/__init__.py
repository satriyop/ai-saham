"""
Domain value objects.

Value objects are immutable objects that represent domain concepts
without unique identity. They are defined by their attributes.

Layer: Domain
"""

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile
from src.domain.value_objects.sentiment import (
    HeadlineResult,
    Sentiment,
    SentimentSnapshot,
)

__all__ = [
    "HeadlineResult",
    "IndicatorSnapshot",
    "RiskAssessment",
    "RiskLevel",
    "RiskProfile",
    "Sentiment",
    "SentimentSnapshot",
]
