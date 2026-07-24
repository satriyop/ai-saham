"""
Price-structure calculations for the ticker dashboard.

Pure helpers over OHLCV candles (+ optional 52w fundamentals).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PriceStructure:
    """Compact market-structure snapshot derived from local candles."""

    as_of: date
    close: Decimal
    change_1d_pct: float | None
    change_5d_pct: float | None
    change_20d_pct: float | None
    high_52w: Decimal | None
    low_52w: Decimal | None
    range_52w_pct: float | None
    volume: int | None
    avg_volume_20d: float | None
    volume_vs_20d: float | None


def _pct_change(latest: Decimal, prior: Decimal | None) -> float | None:
    if prior is None or prior == 0:
        return None
    return float((latest - prior) / prior * Decimal("100"))


def _close_n_sessions_ago(candles_asc: list, sessions: int) -> Decimal | None:
    """Return close from `sessions` trading sessions before the latest bar."""
    if sessions <= 0 or len(candles_asc) <= sessions:
        return None
    return candles_asc[-(sessions + 1)].close


def _avg_volume(candles_asc: list, sessions: int) -> float | None:
    if sessions <= 0 or len(candles_asc) < sessions:
        return None
    window = candles_asc[-sessions:]
    return sum(int(c.volume) for c in window) / float(sessions)


def _range_position(close: Decimal, low: Decimal | None, high: Decimal | None) -> float | None:
    if low is None or high is None:
        return None
    span = high - low
    if span <= 0:
        return None
    return float((close - low) / span * Decimal("100"))


def compute_price_structure(
    candles: list,
    *,
    week52_high: Decimal | float | None = None,
    week52_low: Decimal | float | None = None,
) -> PriceStructure | None:
    """Build structure metrics from ascending or unsorted candles.

    Returns None when no candles are available.
    """
    if not candles:
        return None

    candles_asc = sorted(candles, key=lambda c: c.date)
    latest = candles_asc[-1]
    close = latest.close

    high_52w = Decimal(str(week52_high)) if week52_high is not None else None
    low_52w = Decimal(str(week52_low)) if week52_low is not None else None
    if high_52w is None or low_52w is None:
        # Fallback to available candle window when fundamentals 52w are absent.
        window = candles_asc[-252:] if len(candles_asc) >= 20 else candles_asc
        highs = [c.high for c in window]
        lows = [c.low for c in window]
        if high_52w is None and highs:
            high_52w = max(highs)
        if low_52w is None and lows:
            low_52w = min(lows)

    avg_vol_20 = _avg_volume(candles_asc, 20)
    latest_vol = int(latest.volume)
    vol_vs_20 = None
    if avg_vol_20 is not None and avg_vol_20 > 0:
        vol_vs_20 = latest_vol / avg_vol_20

    return PriceStructure(
        as_of=latest.date,
        close=close,
        change_1d_pct=_pct_change(close, _close_n_sessions_ago(candles_asc, 1)),
        change_5d_pct=_pct_change(close, _close_n_sessions_ago(candles_asc, 5)),
        change_20d_pct=_pct_change(close, _close_n_sessions_ago(candles_asc, 20)),
        high_52w=high_52w,
        low_52w=low_52w,
        range_52w_pct=_range_position(close, low_52w, high_52w),
        volume=latest_vol,
        avg_volume_20d=avg_vol_20,
        volume_vs_20d=vol_vs_20,
    )


def price_structure_to_dict(structure: PriceStructure | None) -> dict | None:
    if structure is None:
        return None
    return {
        "as_of": structure.as_of.isoformat(),
        "close": str(structure.close),
        "change_1d_pct": structure.change_1d_pct,
        "change_5d_pct": structure.change_5d_pct,
        "change_20d_pct": structure.change_20d_pct,
        "high_52w": str(structure.high_52w) if structure.high_52w is not None else None,
        "low_52w": str(structure.low_52w) if structure.low_52w is not None else None,
        "range_52w_pct": structure.range_52w_pct,
        "volume": structure.volume,
        "avg_volume_20d": structure.avg_volume_20d,
        "volume_vs_20d": structure.volume_vs_20d,
    }
