"""Shared deterministic statistics helpers for reports and backtests.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from statistics import mean


def average(
    values: Iterable[float | None],
    *,
    precision: int = 4,
) -> float | None:
    clean = [value for value in values if value is not None]
    return round(mean(clean), precision) if clean else None


def pct_change(
    value: Decimal | float | int,
    base: Decimal | float | int,
    *,
    precision: int = 4,
) -> float:
    base_value = base if isinstance(base, Decimal) else Decimal(str(base))
    if base_value == 0:
        return 0.0
    value_decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    return round(float((value_decimal - base_value) / base_value * Decimal("100")), precision)


def interpolate(
    value: float,
    low_value: float,
    high_value: float,
    low_score: float,
    high_score: float,
) -> float:
    if high_value == low_value:
        return high_score
    progress = (value - low_value) / (high_value - low_value)
    return low_score + progress * (high_score - low_score)


def foreign_vwap_discount_pct(
    foreign_vwap: Decimal | float | int | None,
    current_price: Decimal | float | int | None,
    *,
    precision: int | None = None,
) -> float | None:
    if foreign_vwap is None or current_price is None:
        return None
    current = current_price if isinstance(current_price, Decimal) else Decimal(str(current_price))
    if current <= 0:
        return None
    vwap = foreign_vwap if isinstance(foreign_vwap, Decimal) else Decimal(str(foreign_vwap))
    if vwap <= 0:
        return None
    result = float((vwap - current) / current * Decimal("100"))
    return round(result, precision) if precision is not None else result


def win_rate(
    values: Iterable[float | None],
    *,
    precision: int = 2,
) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(1 for value in clean if value > 0) / len(clean) * 100, precision)


def profit_factor(
    pnl_values: Iterable[Decimal | float | int],
    *,
    precision: int = 4,
) -> float | None:
    gains = Decimal("0")
    losses = Decimal("0")
    for pnl in pnl_values:
        value = pnl if isinstance(pnl, Decimal) else Decimal(str(pnl))
        if value > 0:
            gains += value
        elif value < 0:
            losses += abs(value)

    if losses == 0:
        return None if gains == 0 else float("inf")
    return round(float(gains / losses), precision)


def max_drawdown_pct(
    equity_values: Iterable[Decimal | float | int],
    *,
    precision: int = 4,
) -> float:
    peak: Decimal | None = None
    max_drawdown = Decimal("0")
    for equity in equity_values:
        value = equity if isinstance(equity, Decimal) else Decimal(str(equity))
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            drawdown = (value - peak) / peak * Decimal("100")
            if drawdown < max_drawdown:
                max_drawdown = drawdown
    return round(float(max_drawdown), precision)
