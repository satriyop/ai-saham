"""SwingTuningReviewStore port.

Layer: Domain port
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SwingTuningReviewStore(ABC):
    @abstractmethod
    def append(self, record: dict) -> bool:
        """Append one swing tuning review record."""

    @abstractmethod
    def read_all(self) -> list[dict]:
        """Return all saved swing tuning review records."""
