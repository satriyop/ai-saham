"""Market-data helpers for swing analysis workflow evidence."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from src.domain.value_objects.benchmark_symbol import canonicalize_ticker

if TYPE_CHECKING:
    from src.domain.ports.market_data_repository import MarketDataRepository


def benchmark_return_from_repository(
    repository: "MarketDataRepository",
    *,
    benchmark: str,
    end_date: date,
    lookback: int,
    min_valid: int,
) -> float | None:
    try:
        candles = repository.get_candles(
            canonicalize_ticker(benchmark),
            end_date=end_date,
        )
    except Exception:
        return None
    return simple_return(candles, lookback=lookback, min_valid=min_valid)


def simple_return(
    candles: list[Any] | tuple[Any, ...],
    *,
    lookback: int,
    min_valid: int,
) -> float | None:
    sorted_candles = sorted(candles, key=lambda c: c.date)
    window = sorted_candles[-lookback:] if len(sorted_candles) >= lookback else sorted_candles
    valid = [c for c in window if getattr(c, "close", None) and float(c.close) > 0.0]
    if len(valid) < min_valid:
        return None
    reference = float(valid[0].close)
    if reference <= 0.0:
        return None
    return (float(valid[-1].close) - reference) / reference
