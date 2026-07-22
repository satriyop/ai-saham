"""Generation-safe controller for stateful Discover candidate workbench capabilities.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistRequest,
    CompareScreenWatchlistUseCase,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsRequest,
    ListScreenWatchlistsUseCase,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistRequest,
    SaveScreenWatchlistResult,
)

UniverseLoader = Callable[..., Any]
AccumulationWorkflow = Callable[..., Any]
StateListener = Callable[[ScreenState], None]
UiDispatcher = Callable[..., object]


@dataclass
class DiscoverWorkspaceState:
    active_tab: str = "ACCUMULATION"
    universe_label: str = "lq45"
    window: int = 7
    is_multi_window: bool = False
    min_streak: int = 0
    min_foreign_flow_score: float | None = 50.0
    min_signal_score: float | None = None
    min_piotroski: int = 0
    squeeze_only: bool = False
    vwap_only: bool = False
    sort_by: str = "canonical"
    selected_ticker: str | None = None
    selected_index: int = 0
    saved_watchlist_name: str | None = None


class DiscoverController:
    """Orchestrate stateful Discover tabs: Universe, Accumulation, and Saved/Compare."""

    def __init__(
        self,
        load_universe: UniverseLoader,
        run_accumulation: AccumulationWorkflow,
        list_watchlists: ListScreenWatchlistsUseCase | None = None,
        compare_watchlist: CompareScreenWatchlistUseCase | None = None,
        save_watchlist: Any = None,
    ) -> None:
        self._load_universe = load_universe
        self._run_accumulation = run_accumulation
        self._list_watchlists = list_watchlists
        self._compare_watchlist = compare_watchlist
        self._save_watchlist = save_watchlist
        self._tracker = ScreenStateTracker()
        self.workspace = DiscoverWorkspaceState()

    @property
    def state(self) -> ScreenState:
        return self._tracker.state

    def begin(self) -> int:
        return self._tracker.begin()

    def cancel_current(self) -> bool:
        return self._tracker.cancel_current()

    def execute_universe_generation(
        self,
        generation: int,
        universe_label: str,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Run universe view query."""
        try:
            res = self._load_universe(universe_label)
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        dispatch(self._deliver_success, generation, res, ScreenStatus.READY, listener)

    def execute_accumulation_generation(
        self,
        generation: int,
        request: RunAccumulationScreenWorkflowRequest,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Run accumulation screening workflow for the given typed request."""
        try:
            res = self._run_accumulation(request)
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        dispatch(self._deliver_success, generation, res, ScreenStatus.READY, listener)

    def execute_list_watchlists_generation(
        self,
        generation: int,
        request: ListScreenWatchlistsRequest,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Fetch saved watchlist summaries and optional snapshot entries."""
        if self._list_watchlists is None:
            dispatch(
                self._deliver_failure,
                generation,
                RuntimeError("ListWatchlists capability not configured."),
                listener,
            )
            return
        try:
            res = self._list_watchlists.execute(request)
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        dispatch(self._deliver_success, generation, res, ScreenStatus.READY, listener)

    def execute_compare_watchlist_generation(
        self,
        generation: int,
        request: CompareScreenWatchlistRequest,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Compare saved snapshot against fresh screen."""
        if self._compare_watchlist is None:
            dispatch(
                self._deliver_failure,
                generation,
                RuntimeError("CompareWatchlist capability not configured."),
                listener,
            )
            return
        try:
            res = self._compare_watchlist.execute(request)
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        dispatch(self._deliver_success, generation, res, ScreenStatus.READY, listener)

    def save_current_snapshot(
        self, name: str, candidates: list[AccumulationCandidate], universe: str, window_days: int
    ) -> SaveScreenWatchlistResult | None:
        if self._save_watchlist is None:
            return None
        req = SaveScreenWatchlistRequest(
            name=name,
            candidates=candidates,
            universe=universe,
            window_days=window_days,
        )
        return self._save_watchlist.execute(req)

    def _deliver_success(
        self,
        generation: int,
        payload: Any,
        status: ScreenStatus,
        listener: StateListener,
    ) -> None:
        if self._tracker.complete_current(generation, payload=payload, status=status):
            listener(self._tracker.state)

    def _deliver_failure(
        self,
        generation: int,
        error: Exception,
        listener: StateListener,
    ) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)
