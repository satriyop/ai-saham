"""
Save screener results to a named watchlist snapshot.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


class WatchlistRepository(Protocol):
    """Port: persist and retrieve named screener snapshots."""

    def save_snapshot(self, entries: list[ScreenSnapshotEntry]) -> None: ...


@dataclass(frozen=True)
class SaveScreenWatchlistRequest:
    name: str
    candidates: list[AccumulationCandidate]
    universe: str
    window_days: int


@dataclass(frozen=True)
class SaveScreenWatchlistResult:
    saved_count: int
    name: str


class SaveScreenWatchlistUseCase:
    """Build snapshot entries from screener candidates and persist them."""

    def __init__(self, repository: WatchlistRepository) -> None:
        self._repository = repository

    def execute(self, request: SaveScreenWatchlistRequest) -> SaveScreenWatchlistResult:
        now = datetime.now()
        entries = [
            ScreenSnapshotEntry(
                name=request.name,
                saved_at=now,
                universe=request.universe,
                window_days=request.window_days,
                ticker=c.ticker,
                rank=i + 1,
                accum_score=c.accum_score,
                signal_score=(
                    c.signal_assessment.assessment.score
                    if c.signal_assessment
                    else None
                ),
                consecutive_streak=c.consecutive_streak,
                net_buy_ratio=c.net_buy_ratio,
                bci_label=c.bci_label,
            )
            for i, c in enumerate(request.candidates)
        ]
        self._repository.save_snapshot(entries)
        return SaveScreenWatchlistResult(
            saved_count=len(entries),
            name=request.name,
        )
