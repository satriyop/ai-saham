"""Port: ticker notation/status provider."""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.ticker_notation import TickerNotationSnapshot


class TickerNotationProvider(ABC):
    @abstractmethod
    def get_notation(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        """Return ticker notation/status context from an external source.

        as_of_date=None keeps current/live behavior. Historical callers must
        receive only snapshots fetched on or before as_of_date.
        """
        ...
