"""
Use Case: GetSystemStatus

Retrieves data provider health and calculates database freshness against target cache rules.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import List

from src.domain.ports.system_status_provider import ProviderStatusDto, SystemStatusProvider


@dataclass(frozen=True)
class FreshnessItem:
    table: str
    source: str
    latest: str
    count: int
    status: str
    days_behind: int


@dataclass(frozen=True)
class SystemStatusResponse:
    providers: List[ProviderStatusDto]
    freshness: List[FreshnessItem]


class GetSystemStatusUseCase:
    """Use case to fetch provider health status and calculate cache freshness states."""

    def __init__(self, provider: SystemStatusProvider) -> None:
        self._provider = provider

    def execute(self) -> SystemStatusResponse:
        """Execute the system status checks and calculate status levels."""
        providers = self._provider.check_provider_health()
        freshness_dtos = self._provider.get_data_freshness()

        today = date.today()
        freshness_items = []
        for item in freshness_dtos:
            days_behind = 999
            stale = False
            if item.latest:
                try:
                    latest = datetime.strptime(item.latest, "%Y-%m-%d").date()
                    days_behind = (today - latest).days
                except ValueError:
                    days_behind = 0
                stale = days_behind > 5

            if stale:
                status = "stale"
            elif days_behind == 0 and item.latest:
                status = "today"
            elif days_behind == 1:
                status = "yesterday"
            elif days_behind <= 5:
                status = "current"
            else:
                status = "unknown"

            freshness_items.append(
                FreshnessItem(
                    table=item.table,
                    source=item.source,
                    latest=item.latest or "—",
                    count=item.count,
                    status=status,
                    days_behind=days_behind,
                )
            )

        # Sort freshness results by table name and then by source for consistent presentation
        sorted_freshness = sorted(freshness_items, key=lambda x: (x.table, x.source))

        return SystemStatusResponse(providers=providers, freshness=sorted_freshness)
