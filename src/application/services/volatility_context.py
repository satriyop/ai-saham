"""Shared ATR/volatility classification used by plan swing and signal fingerprints.

Single source of truth so the two call sites cannot drift: plan swing's
diagnostic volatility panel and the persisted SignalObservationFingerprint
volatility fields must always agree on bucket/multiplier logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class VolatilityContext:
    atr_at_signal: float | None
    atr_pct_at_signal: float | None
    volatility_bucket_at_signal: str
    volatility_size_multiplier_at_signal: float


def build_volatility_context(
    *,
    atr_value: Decimal | float | None,
    latest_close: Decimal | float | None,
) -> VolatilityContext:
    atr_float = float(atr_value) if atr_value is not None else None
    close_float = float(latest_close) if latest_close is not None else None
    atr_pct = (
        round((atr_float / close_float) * 100.0, 4)
        if atr_float is not None and close_float and close_float > 0
        else None
    )
    bucket, size_multiplier = _classify(atr_pct)
    return VolatilityContext(
        atr_at_signal=atr_float,
        atr_pct_at_signal=atr_pct,
        volatility_bucket_at_signal=bucket,
        volatility_size_multiplier_at_signal=size_multiplier,
    )


def _classify(atr_pct: float | None) -> tuple[str, float]:
    if atr_pct is None:
        return "UNKNOWN", 1.0
    if atr_pct < 2.0:
        return "LOW", 1.0
    if atr_pct < 5.0:
        return "NORMAL", 1.0
    if atr_pct < 8.0:
        return "HIGH", 0.75
    return "EXTREME", 0.50
