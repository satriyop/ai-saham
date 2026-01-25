"""
Relative Strength Index (RSI) indicator.

Pure domain logic with no external dependencies.
Implements Wilder's smoothed moving average for professional-grade accuracy.

Layer: Domain
Dependencies: None (only standard library + domain entities)
"""

from datetime import date
from decimal import Decimal

from src.domain.entities.candle import Candle


def calculate_rsi(
    candles: list[Candle],
    period: int = 14,
) -> list[tuple[date, Decimal]]:
    """
    Calculate RSI using Wilder's smoothed moving average.

    Algorithm:
    1. Calculate price changes: delta = close(t) - close(t-1)
    2. Separate gains (positive deltas) and losses (absolute negative deltas)
    3. First avg_gain/avg_loss = SMA of first `period` values (the seed)
    4. Subsequent: avg(t) = (avg(t-1) * (period-1) + current) / period
    5. RS = avg_gain / avg_loss
    6. RSI = 100 - (100 / (1 + RS))

    Special cases:
    - avg_loss = 0: RSI = 100 (all gains, no losses)
    - avg_gain = 0: RSI = 0 (all losses, no gains)

    Args:
        candles: List of Candle entities, sorted by date ascending
        period: Number of periods for RSI calculation (default 14)

    Returns:
        List of (date, rsi_value) tuples, starting from index `period`.
        Empty list if insufficient data (need at least period + 1 candles).

    Raises:
        ValueError: If period < 1

    Example:
        >>> candles = [...]  # 100 candles
        >>> rsi_values = calculate_rsi(candles, period=14)
        >>> len(rsi_values)  # 86 (100 - 14)
        86
    """
    # Validation
    if period < 1:
        raise ValueError("Period must be at least 1")

    # Edge case: need at least period + 1 candles for first RSI
    # (period + 1 prices = period deltas)
    if len(candles) < period + 1:
        return []

    # Extract close prices
    prices = [candle.close for candle in candles]

    # Calculate price deltas
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # Separate gains and losses
    gains = [max(d, Decimal("0")) for d in deltas]
    losses = [abs(min(d, Decimal("0"))) for d in deltas]

    result: list[tuple[date, Decimal]] = []

    # Step 1: Calculate initial averages (SMA seed of first `period` values)
    avg_gain = sum(gains[:period], Decimal("0")) / period
    avg_loss = sum(losses[:period], Decimal("0")) / period

    # Calculate first RSI at index `period` (candle index)
    rsi_value = _calculate_rsi_value(avg_gain, avg_loss)
    result.append((candles[period].date, rsi_value))

    # Step 2: Apply Wilder's smoothing for remaining values
    # Formula: avg(t) = (avg(t-1) * (period-1) + current) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        rsi_value = _calculate_rsi_value(avg_gain, avg_loss)
        # Candle index is delta index + 1
        result.append((candles[i + 1].date, rsi_value))

    return result


def _calculate_rsi_value(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    """
    Calculate RSI from average gain and loss.

    Formula: RSI = 100 - (100 / (1 + RS))
    where RS = avg_gain / avg_loss

    Special cases:
    - avg_loss = 0: RSI = 100 (all gains)
    - avg_gain = 0: RSI = 0 (all losses)
    """
    if avg_loss == Decimal("0"):
        return Decimal("100")
    if avg_gain == Decimal("0"):
        return Decimal("0")

    rs = avg_gain / avg_loss
    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
    return rsi
