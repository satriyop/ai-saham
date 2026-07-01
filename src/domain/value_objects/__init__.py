"""
Domain value objects.

Value objects are immutable objects that represent domain concepts
without unique identity. They are defined by their attributes.

Layer: Domain
"""

from src.domain.value_objects.backtest_result import BacktestResult
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel
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
from src.domain.value_objects.ticker_classifier import is_non_idx_ticker

__all__ = [
    "ArtifactType",
    "BacktestResult",
    "DriftInfo",
    "HeadlineResult",
    "IndicatorSnapshot",
    "RiskAssessment",
    "RiskLevel",
    "Sentiment",
    "SentimentSnapshot",
    "SkillAnnotation",
    "SkillMetadata",
    "TradeAction",
    "is_non_idx_ticker",
]
