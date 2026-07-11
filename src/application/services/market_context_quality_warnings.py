"""
Market context data-quality warnings — staleness and coverage checks.

Pure functions, no calendar or repository dependency. Used by
BuildMarketContextUseCase.

Layer: Application
"""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.entities.candle import Candle
from src.domain.value_objects.market_context import ContextFactor


def market_context_staleness_warning(
    vix_candles: list[Candle],
    eido_candles: list[Candle],
    usd_idr_candles: list[Candle],
    as_of: date,
    stale_business_day_gap: int,
) -> str | None:
    stale = []
    named_candles = [("VIX", vix_candles), ("EIDO", eido_candles), ("USD/IDR", usd_idr_candles)]
    for name, candles in named_candles:
        if candles and _business_day_gap(candles[-1].date, as_of) > stale_business_day_gap:
            stale.append(f"{name} ({candles[-1].date})")
    if not stale:
        return None
    return f"Using T-1 data for: {', '.join(stale)}. Run: saham fetch market --universe lq45"


def market_context_coverage_warning(
    factors: list[ContextFactor], unavailable_ratio: float,
) -> str | None:
    enabled = [f for f in factors if f.enabled]
    unavailable = [f for f in enabled if f.score is None]
    if enabled and len(unavailable) / len(enabled) >= unavailable_ratio:
        names = ", ".join(f.name for f in unavailable)
        return f"{len(unavailable)}/{len(enabled)} factors unavailable: {names}"
    return None


def _business_day_gap(start: date, end: date) -> int:
    """Count weekday-only days between start (exclusive) and end (inclusive)."""
    days, current = 0, start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # Mon–Fri
            days += 1
        current += timedelta(days=1)
    return days
