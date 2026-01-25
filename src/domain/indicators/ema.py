"""
Exponential Moving Average (EMA) indicator.

Pure domain logic with no external dependencies.
Uses SMA-seeded initialization for professional-grade accuracy.

Layer: Domain
Dependencies: None (only standard library + domain entities)
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from src.domain.entities.candle import Candle

PriceField = Literal["open", "high", "low", "close"]


def calculate_ema(
    candles: list[Candle],
    period: int = 20,
    price_field: PriceField = "close",
) -> list[tuple[date, Decimal]]:
    """
    Calculate Exponential Moving Average using SMA-seeded initialization.

    Algorithm:
    1. EMA_0 = SMA(period) of first `period` candles (the seed)
    2. EMA(t) = Price(t) * k + EMA(t-1) * (1 - k)
       where k = 2 / (period + 1)

    This matches TradingView, Bloomberg, and TA-Lib behavior.

    Args:
        candles: List of Candle entities, sorted by date ascending
        period: Number of periods for moving average (default 20)
        price_field: Which price to use - "open", "high", "low", "close" (default "close")

    Returns:
        List of (date, ema_value) tuples, starting from index period-1.
        First value is the SMA seed, subsequent values use EMA formula.
        Empty list if insufficient data.

    Raises:
        ValueError: If period < 1 or price_field invalid

    Example:
        >>> candles = [...]  # 100 candles
        >>> ema_values = calculate_ema(candles, period=20)
        >>> len(ema_values)  # 81 (100 - 20 + 1)
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

    # Calculate smoothing multiplier: k = 2 / (period + 1)
    k = Decimal("2") / (period + 1)
    one_minus_k = Decimal("1") - k

    result: list[tuple[date, Decimal]] = []

    # Step 1: Calculate SMA of first `period` candles as seed
    sma_seed = sum(prices[:period], Decimal("0")) / period
    result.append((candles[period - 1].date, sma_seed))

    # Step 2: Apply EMA formula for remaining candles
    # EMA(t) = Price(t) * k + EMA(t-1) * (1 - k)
    ema_prev = sma_seed
    for i in range(period, len(candles)):
        ema_current = prices[i] * k + ema_prev * one_minus_k
        result.append((candles[i].date, ema_current))
        ema_prev = ema_current

    return result
