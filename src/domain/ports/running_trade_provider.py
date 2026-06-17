"""
Port: RunningTradeProvider

Fetches recent executed trade ticks for a ticker from a market data source.
Implementations may use Stockbit or any other real-time trade feed.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.entities.trade_tick import TradeTick


class RunningTradeProvider(ABC):
    """Abstract source for real-time executed trade ticks."""

    @abstractmethod
    def fetch_running_trade(self, ticker: str, limit: int = 80) -> list[TradeTick]:
        """Return the most recent executed trade ticks for ticker.

        Args:
            ticker: IDX ticker symbol.
            limit:  Maximum number of ticks to return (most recent first).

        Returns:
            List of TradeTick objects, newest first.
            Returns empty list on error — never raises.
        """
        ...
