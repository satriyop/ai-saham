"""Compare a saved watchlist snapshot against a fresh accumulation screen run.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.screen_accum_result_projector import (
    ScreenAccumMultiProjection,
    ScreenAccumSingleProjection,
)
from src.application.use_case.compare_screen_snapshots_use_case import (
    ScreenCompareResult,
    compare_screen_snapshots,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ScreenWatchlistSummary,
    WatchlistQueryRepository,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
    RunAccumulationScreenWorkflowUseCase,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


class WatchlistNotFoundError(Exception):
    """Raised when a requested watchlist snapshot does not exist."""


@dataclass(frozen=True)
class CompareScreenWatchlistRequest:
    name: str
    screen_request: RunAccumulationScreenWorkflowRequest


@dataclass(frozen=True)
class CompareScreenWatchlistResult:
    saved_summary: ScreenWatchlistSummary
    fresh_projection: ScreenAccumSingleProjection | ScreenAccumMultiProjection
    comparison: ScreenCompareResult


class CompareScreenWatchlistUseCase:
    """Load saved snapshot, run fresh screen, and produce structured compare result."""

    def __init__(
        self,
        watchlist_repository: WatchlistQueryRepository,
        screen_workflow_use_case: RunAccumulationScreenWorkflowUseCase,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._screen_workflow_use_case = screen_workflow_use_case

    def execute(
        self, request: CompareScreenWatchlistRequest
    ) -> CompareScreenWatchlistResult:
        snapshot_entries = self._watchlist_repository.get_latest_snapshot(request.name)
        if not snapshot_entries:
            raise WatchlistNotFoundError(
                f"No saved watchlist snapshot found under name '{request.name}'."
            )

        saved_at = snapshot_entries[0].saved_at
        saved_universe = snapshot_entries[0].universe
        saved_window = snapshot_entries[0].window_days
        summary = ScreenWatchlistSummary(
            name=request.name,
            latest_saved_at=saved_at,
            universe=saved_universe,
            window_days=saved_window,
            ticker_count=len(snapshot_entries),
        )

        fresh_projection = self._screen_workflow_use_case.execute(request.screen_request)

        fresh_tickers: list[str] = []
        fresh_scores: dict[str, tuple[float, float | None]] = {}
        fresh_ranks: dict[str, int] = {}

        if isinstance(fresh_projection, ScreenAccumMultiProjection):
            candidates = [row.candidate for row in fresh_projection.rows]
        else:
            candidates = list(fresh_projection.candidates)

        for rank, c in enumerate(candidates, 1):
            fresh_tickers.append(c.ticker)
            composite = (
                c.signal_assessment.assessment.score
                if c.signal_assessment
                else None
            )
            fresh_scores[c.ticker] = (c.foreign_flow_score, composite)
            fresh_ranks[c.ticker] = rank

        comparison = compare_screen_snapshots(
            snapshot=snapshot_entries,
            fresh_tickers=fresh_tickers,
            fresh_scores=fresh_scores,
            fresh_ranks=fresh_ranks,
            snapshot_name=request.name,
        )

        return CompareScreenWatchlistResult(
            saved_summary=summary,
            fresh_projection=fresh_projection,
            comparison=comparison,
        )
