"""
Port: InsiderActivityProvider

Provides insider ownership transaction history for a ticker.
Implementations source data from Stockbit (IDX filing disclosures).

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.insider_transaction import InsiderTransaction


class InsiderActivityProvider(ABC):
    """Abstract source for insider buy/sell transaction data."""

    @abstractmethod
    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]:
        """Return insider transactions for ticker in [from_date, to_date].

        Args:
            ticker:      IDX ticker symbol.
            from_date:   Start of the lookback window (inclusive).
            to_date:     End of the lookback window (inclusive).
            action_type: "BUY", "SELL", or "ALL" (both).
            as_of_date:  None for live/latest behavior, where implementations may
                         use TTL and network. A date value means point-in-time
                         replay: cache-only, using only rows fetched on or before
                         that date.

        Returns:
            List of InsiderTransaction objects, newest first.
            Returns empty list on error — never raises.
        """
        ...
