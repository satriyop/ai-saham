"""Pure technical feature helpers for accumulation screening."""

from __future__ import annotations

from decimal import Decimal


def compute_accumulation_rsi(candles: list, period: int) -> float | None:
    """Wilder's RSI from candle close prices."""
    closes = [float(c.close) for c in candles]
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    # Initial averages (SMA seed)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's smoothing for the rest
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_accumulation_trend(
    candles: list,
    sma_period: int,
    *,
    trend_threshold_pct: float,
) -> str:
    """Classify trend relative to SMA."""
    if len(candles) < sma_period:
        return "SIDE"

    recent = candles[-sma_period:]
    sma = sum(float(c.close) for c in recent) / sma_period
    current = float(candles[-1].close)
    pct_diff = (current - sma) / sma * 100

    if pct_diff > trend_threshold_pct:
        return "UP"
    elif pct_diff < -trend_threshold_pct:
        return "DOWN"
    return "SIDE"


def compute_bb_widths(candles: list, period: int = 20) -> list[float]:
    """BB Width = (upper - lower) / mid * 100 for each candle."""
    closes = [float(c.close) for c in candles]
    if len(closes) < period:
        return []
    out = []
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mid = sum(window) / period
        if mid <= 0:
            out.append(0.0)
            continue
        std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
        out.append(4.0 * std / mid * 100)  # (upper-lower)/mid*100, upper=mid+2σ
    return out


def compute_bb_squeeze(
    candles: list, period: int = 20, history: int = 60
) -> tuple[float | None, float | None]:
    """Return (bb_width_now, percentile_rank_vs_last_N_days).

    percentile=0.0 means current width is the tightest in `history` days
    (maximum squeeze). percentile=1.0 means widest (expanding volatility).
    """
    widths = compute_bb_widths(candles, period)
    if not widths:
        return None, None
    bb_width_now = widths[-1]
    if len(widths) < history:
        return bb_width_now, None
    recent = widths[-history:]
    rank = sum(1 for w in recent if w <= bb_width_now) / len(recent)
    return bb_width_now, rank


def compute_resistance_levels(
    candles: list,
    current_price: Decimal,
    *,
    resistance_ma_period: int,
    resistance_high_period: int,
) -> tuple[Decimal | None, Decimal | None, float | None]:
    """Compute MA200, 52-week high, and % distance to nearest resistance above price.

    Returns (ma200, week52_high, nearest_resistance_pct).
    nearest_resistance_pct is None if no resistance level is above current price.
    Positive value = resistance is X% above current price (more headroom = better).
    """
    if not candles or current_price <= 0:
        return None, None, None

    ma200: Decimal | None = None
    if len(candles) >= resistance_ma_period:
        ma200 = Decimal(
            str(sum(c.close for c in candles[-resistance_ma_period:]) / resistance_ma_period)
        )

    week52_high: Decimal | None = None
    if len(candles) >= 1:
        week52_high = max(c.high for c in candles[-resistance_high_period:])

    resistances: list[float] = []
    for level in (ma200, week52_high):
        if level is not None and level > current_price:
            pct = float((level - current_price) / current_price * 100)
            resistances.append(pct)

    nearest_resistance_pct = min(resistances) if resistances else None
    return ma200, week52_high, nearest_resistance_pct
