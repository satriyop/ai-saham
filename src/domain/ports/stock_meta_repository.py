"""Port: stock metadata persistence."""

from abc import ABC, abstractmethod

from src.domain.entities.stock_meta import StockMeta


class StockMetaRepository(ABC):
    @abstractmethod
    def get(self, ticker: str) -> StockMeta | None: ...

    @abstractmethod
    def save(self, meta: StockMeta) -> None: ...

    @abstractmethod
    def needs_refresh(self, ticker: str, ttl_days: int) -> bool:
        """True if ticker has no record or fetched_at is older than ttl_days."""
        ...
