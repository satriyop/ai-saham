"""Port: ticker notation/status persistence."""

from abc import ABC, abstractmethod

from src.domain.value_objects.ticker_notation import TickerNotationSnapshot


class TickerNotationRepository(ABC):
    @abstractmethod
    def get_notation(self, ticker: str) -> TickerNotationSnapshot | None: ...

    @abstractmethod
    def save_notation(self, snapshot: TickerNotationSnapshot) -> None: ...

    @abstractmethod
    def is_cache_fresh(self, ticker: str) -> bool: ...
