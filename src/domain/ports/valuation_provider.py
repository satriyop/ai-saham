"""Port: ValuationProvider — supply per-ticker valuation metrics.

Layer: Domain
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.valuation_metrics import ValuationMetrics


class ValuationProvider(ABC):
    @abstractmethod
    def get_valuation(self, ticker: str) -> ValuationMetrics | None:
        """Return cached or freshly fetched valuation metrics, or None."""

    @abstractmethod
    def is_cache_fresh(self, ticker: str) -> bool:
        """True if the cache for this ticker is within its TTL."""
