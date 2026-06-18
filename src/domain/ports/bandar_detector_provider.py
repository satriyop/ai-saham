"""
Port: BandarDetectorProvider

Provides Stockbit's bandar detector accumulation/distribution signal for a ticker
on a given trading session.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot


class BandarDetectorProvider(ABC):
    """Abstract source for per-ticker bandar detector signal."""

    @abstractmethod
    def get_snapshot(
        self, ticker: str, session_date: date | None = None
    ) -> BandarDetectorSnapshot | None:
        """Return bandar detector snapshot for ticker on session_date (default: today).

        Returns:
            BandarDetectorSnapshot, or None if data unavailable.
            Never raises.
        """
        ...
