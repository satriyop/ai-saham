"""Indicator-on-computed-series helpers for formula evaluation.

This module provides functions for applying indicators (SMA, EMA) to
already-computed arbitrary series. It does not use domain indicator classes
or registry lookups — only pure series math.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.formula.exceptions import FormulaEvaluationError


def apply_indicator_to_series(
    name: str,
    series: list[Decimal],
    period: int,
) -> list[Decimal]:
    """Apply an indicator function to a computed series.

    This is used when the indicator is applied to a computed series
    rather than raw price data (e.g., SMA(RSI(14), 10)).

    The implementation depends on the indicator type:
    - SMA: Simple moving average of the series
    - EMA: Exponential moving average of the series
    - Other indicators raise FormulaEvaluationError

    Args:
        name: Indicator name.
        series: Input series values.
        period: Calculation period.

    Returns:
        List of Decimal values.

    Raises:
        FormulaEvaluationError: If the indicator does not support
            series-to-series computation.
    """
    if not series:
        return []

    if name == "SMA":
        return compute_sma_on_series(series, period)
    elif name == "EMA":
        return compute_ema_on_series(series, period)
    else:
        raise FormulaEvaluationError(
            f"Indicator {name} cannot be applied to computed series. "
            "Only SMA and EMA support series-to-series computation.",
            formula_name=name,
        )


def compute_sma_on_series(series: list[Decimal], period: int) -> list[Decimal]:
    """Compute SMA on an arbitrary series.

    Args:
        series: Input values.
        period: SMA period.

    Returns:
        SMA values (length = len(series) - period + 1).
    """
    if len(series) < period:
        return []

    result: list[Decimal] = []
    window_sum = sum(series[:period])
    result.append(window_sum / period)

    for i in range(period, len(series)):
        window_sum = window_sum - series[i - period] + series[i]
        result.append(window_sum / period)

    return result


def compute_ema_on_series(series: list[Decimal], period: int) -> list[Decimal]:
    """Compute EMA on an arbitrary series.

    Uses standard EMA formula: EMA = price * k + EMA_prev * (1 - k)
    where k = 2 / (period + 1)

    Args:
        series: Input values.
        period: EMA period.

    Returns:
        EMA values (length = len(series) - period + 1).
    """
    if len(series) < period:
        return []

    multiplier = Decimal(2) / (Decimal(period) + 1)
    one_minus_k = Decimal(1) - multiplier

    initial_sma = sum(series[:period]) / period
    result: list[Decimal] = [initial_sma]

    for i in range(period, len(series)):
        ema = series[i] * multiplier + result[-1] * one_minus_k
        result.append(ema)

    return result
