"""Port: stock metadata provider (external data source)."""

from abc import ABC, abstractmethod

from src.domain.entities.stock_meta import StockMeta


class StockMetaProvider(ABC):
    @abstractmethod
    def fetch(self, ticker: str) -> StockMeta | None:
        """
        Fetch current metadata for a ticker from the external source.

        Args:
            ticker: IDX ticker without suffix (e.g. 'BBCA').

        Returns:
            StockMeta if found, None if the source has no data for this ticker.
        """
        ...
