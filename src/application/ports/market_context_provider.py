"""Market context provider port.

Layer: Application Port
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.value_objects.market_context import MarketContext


class MarketContextProvider(Protocol):
    """Port interface for providing market contexts grouped by date."""

    def evaluate_for_dates(
        self,
        *,
        tickers: list[str],
        replay_dates: list[date],
        benchmark_ticker: str,
    ) -> dict[date, MarketContext]:
        """Evaluate and return market contexts for the given replay dates."""
        ...
