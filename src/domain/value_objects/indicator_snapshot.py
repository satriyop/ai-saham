"""
IndicatorSnapshot value object.

Represents a single point-in-time snapshot of technical indicators for a ticker.
This is a pure domain concept - no behavior, just immutable data.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class IndicatorSnapshot:
    """
    Single point-in-time snapshot of all indicators for a ticker.

    This value object captures the state of SMA, EMA, and RSI at a specific date.
    It is immutable (frozen) and defined by its attributes.

    Attributes:
        date: The date this snapshot represents
        sma: Simple Moving Average value
        ema: Exponential Moving Average value
        rsi: Relative Strength Index value (0-100)
    """

    date: date
    sma: Decimal
    ema: Decimal
    rsi: Decimal
