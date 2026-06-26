"""IndicatorReading — measurement language for technical indicator output."""
from enum import Enum


class IndicatorReading(Enum):
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
