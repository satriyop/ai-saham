"""Candles-only hung-fetch gate: soft-success when session candles are already in DB.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from src.domain.ports.market_data_repository import MarketDataRepository


def candles_only_unavailable_tickers(response: object) -> list[str]:
    """Tickers whose same-session OHLC was unavailable on this candles-only run.

    Prefer ``response.unavailable_tickers`` when the refresh DTO already carries
    it (e.g. after a timeout-retry pass). Otherwise derive from ``ERR:`` candle
    statuses, then ``response.failures``.
    """
    existing = getattr(response, "unavailable_tickers", None)
    if existing is not None:
        return [str(ticker) for ticker in existing]
    from_status = [
        str(item.ticker)
        for item in getattr(response, "ticker_results", []) or []
        if str(getattr(item, "candles_status", "")).startswith("ERR:")
    ]
    if from_status:
        return from_status
    return [str(ticker) for ticker in getattr(response, "failures", []) or []]


def missing_same_session_candle_tickers(
    required_tickers: Sequence[str],
    present_tickers: Sequence[str],
) -> tuple[str, ...]:
    """Return required tickers that have no candle row among ``present_tickers``."""
    present = {ticker.upper() for ticker in present_tickers}
    return tuple(ticker for ticker in required_tickers if ticker.upper() not in present)


def missing_required_session_candles(
    required_tickers: Sequence[str],
    session_date: date,
    market_repository: MarketDataRepository,
) -> tuple[str, ...]:
    """Required stock tickers missing a candle row on ``session_date``."""
    present = market_repository.list_tickers_with_candles_between(session_date, session_date)
    return missing_same_session_candle_tickers(required_tickers, present)


def hung_candles_only_fails_closed(
    *,
    hung_count: int,
    missing_tickers: Sequence[str],
) -> bool:
    """Fail closed when hung fetches left required same-session candles missing."""
    return hung_count > 0 and len(missing_tickers) > 0
