"""
Domain value objects.

Value objects are immutable objects that represent domain concepts
without unique identity. They are defined by their attributes.

Layer: Domain
"""

from src.domain.value_objects.backtest_result import BacktestResult
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile
from src.domain.value_objects.sentiment import (
    HeadlineResult,
    Sentiment,
    SentimentSnapshot,
)
from src.domain.value_objects.skill_annotation import (
    ArtifactType,
    DriftInfo,
    SkillAnnotation,
    SkillMetadata,
)
from src.domain.value_objects.trade_action import TradeAction

__all__ = [
    "ArtifactType",
    "BacktestResult",
    "DriftInfo",
    "HeadlineResult",
    "IndicatorSnapshot",
    "RiskAssessment",
    "RiskLevel",
    "RiskProfile",
    "Sentiment",
    "SentimentSnapshot",
    "SkillAnnotation",
    "SkillMetadata",
    "TradeAction",
]
