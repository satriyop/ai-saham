"""Port: ticker notation/status provider."""

from abc import ABC, abstractmethod

from src.domain.value_objects.ticker_notation import TickerNotationSnapshot


class TickerNotationProvider(ABC):
    @abstractmethod
    def get_notation(self, ticker: str) -> TickerNotationSnapshot | None:
        """Return current ticker notation/status context from an external source."""
        ...
