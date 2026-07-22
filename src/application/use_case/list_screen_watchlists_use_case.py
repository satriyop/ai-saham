"""List saved screen watchlist snapshots.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


class WatchlistQueryRepository(Protocol):
    """Port: list and fetch saved screener snapshots."""

    def list_snapshots(self) -> list[dict]: ...
    def get_latest_snapshot(self, name: str) -> list[ScreenSnapshotEntry]: ...


@dataclass(frozen=True)
class ScreenWatchlistSummary:
    name: str
    latest_saved_at: datetime
    universe: str
    window_days: int
    ticker_count: int


@dataclass(frozen=True)
class ListScreenWatchlistsRequest:
    name: str | None = None


@dataclass(frozen=True)
class ListScreenWatchlistsResult:
    summaries: tuple[ScreenWatchlistSummary, ...]
    selected_entries: tuple[ScreenSnapshotEntry, ...] = ()


class ListScreenWatchlistsUseCase:
    """Retrieve saved watchlist summaries and optionally latest entries for a named watchlist."""

    def __init__(self, repository: WatchlistQueryRepository) -> None:
        self._repository = repository

    def execute(
        self, request: ListScreenWatchlistsRequest | None = None
    ) -> ListScreenWatchlistsResult:
        req = request or ListScreenWatchlistsRequest()
        raw_summaries = self._repository.list_snapshots()
        summaries: list[ScreenWatchlistSummary] = []
        for item in raw_summaries:
            saved_at = item.get("latest_saved_at")
            if isinstance(saved_at, str):
                saved_at = datetime.fromisoformat(saved_at)
            elif not isinstance(saved_at, datetime):
                saved_at = datetime.now()
            summaries.append(
                ScreenWatchlistSummary(
                    name=item["name"],
                    latest_saved_at=saved_at,
                    universe=item.get("universe", ""),
                    window_days=item.get("window_days", 7),
                    ticker_count=item.get("ticker_count", 0),
                )
            )

        selected_entries: list[ScreenSnapshotEntry] = []
        if req.name:
            selected_entries = self._repository.get_latest_snapshot(req.name)

        return ListScreenWatchlistsResult(
            summaries=tuple(summaries),
            selected_entries=tuple(selected_entries),
        )
