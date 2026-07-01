"""
FallbackMarketDataProvider — wraps a primary and fallback MarketDataProvider.

If the primary returns fewer candles than the coverage threshold (default 60%
of expected trading days), the fallback provider is tried. If the fallback also
returns nothing, the primary's (possibly partial) result is returned.

This keeps RefreshMarketDataUseCase unchanged — it still sees one provider.
Coverage threshold: actual_days / expected_trading_days < threshold → try fallback.
Expected trading days is approximated as (end - start).days * 5/7.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider

logger = logging.getLogger(__name__)

_DEFAULT_COVERAGE_THRESHOLD = 0.60  # try fallback if primary returns <60% of expected days


def _expected_trading_days(start: date, end: date) -> int:
    """Approximate trading days in [start, end] as calendar days * 5/7."""
    span = max(0, (end - start).days + 1)
    return max(1, round(span * 5 / 7))


class FallbackMarketDataProvider(MarketDataProvider):
    """Delegates to `primary`; falls back to `fallback` on insufficient coverage.

    The `provider_name`, `volume_unit`, and `price_adjustment_policy` attributes
    reflect whichever provider actually supplied the data (tracked per call).

    Args:
        primary:    First-choice provider (e.g. YahooFinanceProvider).
        fallback:   Second-choice provider (e.g. StockbitHistoricalProvider).
        coverage_threshold: Float in [0, 1]. Below this ratio of expected
            trading days, the fallback is attempted (default 0.60).
    """

    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider,
        coverage_threshold: float = _DEFAULT_COVERAGE_THRESHOLD,
        non_idx_tickers: set[str] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._threshold = coverage_threshold
        self._active_provider: MarketDataProvider = primary
        self._non_idx_tickers = non_idx_tickers or set()

    # Proxy metadata to whichever provider last served data
    @property
    def provider_name(self) -> str:
        return getattr(self._active_provider, "provider_name", "unknown")

    @property
    def volume_unit(self) -> str:
        return getattr(self._active_provider, "volume_unit", "unknown")

    @property
    def price_adjustment_policy(self) -> str:
        return getattr(self._active_provider, "price_adjustment_policy", "unknown")

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        self._active_provider = self._primary
        try:
            primary_candles = self._primary.fetch_daily_ohlcv(ticker, start_date, end_date)
        except Exception as exc:
            logger.debug("FallbackProvider: primary failed for %s (%s), trying fallback", ticker, exc)
            primary_candles = []

        expected = _expected_trading_days(start_date, end_date)
        coverage = len(primary_candles) / expected

        from src.domain.value_objects import is_non_idx_ticker
        if is_non_idx_ticker(ticker, self._non_idx_tickers):
            return primary_candles

        if coverage >= self._threshold:
            return primary_candles

        logger.info(
            "FallbackProvider: %s primary coverage %.0f%% < %.0f%% threshold — trying fallback",
            ticker, coverage * 100, self._threshold * 100,
        )
        try:
            fallback_candles = self._fallback.fetch_daily_ohlcv(ticker, start_date, end_date)
        except Exception as exc:
            logger.debug("FallbackProvider: fallback also failed for %s: %s", ticker, exc)
            fallback_candles = []

        if fallback_candles:
            self._active_provider = self._fallback
            logger.info(
                "FallbackProvider: %s using fallback (%s) — %d candles",
                ticker,
                getattr(self._fallback, "provider_name", "fallback"),
                len(fallback_candles),
            )
            return fallback_candles

        return primary_candles
