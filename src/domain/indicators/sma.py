"""
Simple Moving Average (SMA) indicator.

Pure domain logic with no external dependencies.
Implements sliding window average over price series.

Layer: Domain
Dependencies: None (only standard library + domain entities)
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from src.domain.entities.candle import Candle

PriceField = Literal["open", "high", "low", "close"]


def calculate_sma(
    candles: list[Candle],
    period: int = 20,
    price_field: PriceField = "close",
) -> list[tuple[date, Decimal]]:
    """
    Calculate Simple Moving Average over candle data.

    Algorithm:
    - For each position i >= (period - 1):
      SMA[i] = sum(prices[i-period+1 : i+1]) / period

    Args:
        candles: List of Candle entities, sorted by date ascending
        period: Number of periods for moving average (default 20)
        price_field: Which price to use - "open", "high", "low", "close" (default "close")

    Returns:
        List of (date, sma_value) tuples, starting from index period-1.
        Empty list if insufficient data.

    Raises:
        ValueError: If period < 1 or price_field invalid

    Example:
        >>> candles = [...]  # 100 candles
        >>> sma_values = calculate_sma(candles, period=20)
        >>> len(sma_values)  # 81 (100 - 20 + 1)
        81
    """
    # Validation
    if period < 1:
        raise ValueError("Period must be at least 1")

    if price_field not in ("open", "high", "low", "close"):
        raise ValueError(f"Invalid price_field: {price_field}")

    # Edge case: insufficient data
    if len(candles) < period:
        return []

    # Extract prices using getattr for the specified field
    prices = [getattr(candle, price_field) for candle in candles]

    # Calculate SMA using sliding window
    result: list[tuple[date, Decimal]] = []
    for i in range(period - 1, len(candles)):
        window = prices[i - period + 1 : i + 1]
        sma_value = sum(window, Decimal("0")) / period
        result.append((candles[i].date, sma_value))

    return result
