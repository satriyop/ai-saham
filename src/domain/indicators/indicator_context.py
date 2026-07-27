"""IndicatorContext — shareable output of IndicatorEvaluator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.domain.indicators.indicator_reading import IndicatorReading


@dataclass(frozen=True)
class IndicatorContext:
    sma_reading: IndicatorReading
    ema_reading: IndicatorReading
    rsi_reading: IndicatorReading
    overall: IndicatorReading  # composite: majority of 3
    confidence: int  # 0 / 50 / 100 — how many agree
    sma_value: Decimal
    ema_value: Decimal
    rsi_value: Decimal
    rationale: tuple[str, ...]
