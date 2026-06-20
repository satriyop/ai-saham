"""
Port: SystemStatusProvider

Defines DTOs and the interface for checking data provider health and database data freshness.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ProviderStatusDto:
    name: str
    ok: bool
    label: str
    ms: float


@dataclass(frozen=True)
class TableFreshnessDto:
    table: str
    source: str
    latest: Optional[str]
    count: int


class SystemStatusProvider(ABC):
    """Abstract port for checking provider health and querying database freshness."""

    @abstractmethod
    def check_provider_health(self) -> List[ProviderStatusDto]:
        """Probe data provider endpoints (IDX, Yahoo, Stockbit, AI keys) and return status list."""
        pass

    @abstractmethod
    def get_data_freshness(self) -> List[TableFreshnessDto]:
        """Query database tables and return freshness metrics (row count, latest update date) for each table."""
        pass
