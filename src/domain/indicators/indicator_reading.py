"""IndicatorReading — measurement language for technical indicator output."""

from enum import Enum


class IndicatorReading(Enum):
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"

    @classmethod
    def parse(cls, value: str) -> "IndicatorReading":
        """Parse canonical uppercase and legacy lowercase readings."""
        normalized = value.strip().upper().replace("-", "_")
        for reading in cls:
            if normalized in {reading.name, reading.value}:
                return reading
        valid = [reading.value for reading in cls]
        raise ValueError(f"Invalid indicator reading '{value}'. Must be one of: {valid}")
