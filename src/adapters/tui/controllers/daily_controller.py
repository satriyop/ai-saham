"""Generation-safe controller for Daily command center briefing & update capabilities.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse
from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
    RefreshDailyWorkspaceRequest,
    RefreshDailyWorkspaceResult,
)

DailyLoader = Callable[[], DailyBriefingResponse]
DailyRefresher = Callable[..., RefreshDailyWorkspaceResult]
DailyPreviewer = Callable[[RefreshDailyWorkspaceRequest], DailyWorkspaceRefreshPlan]
StateListener = Callable[[ScreenState], None]
UiDispatcher = Callable[..., object]


class DailyController:
    """Invoke injected briefing and workspace refresh capabilities per explicit generation."""

    def __init__(
        self,
        load_daily: DailyLoader,
        refresh_daily: DailyRefresher | None = None,
        preview_daily: DailyPreviewer | None = None,
    ) -> None:
        self._load_daily = load_daily
        self._refresh_daily = refresh_daily
        self._preview_daily = preview_daily
        self._tracker = ScreenStateTracker()

    @property
    def state(self) -> ScreenState:
        return self._tracker.state

    def begin(self) -> int:
        return self._tracker.begin()

    def cancel_current(self) -> bool:
        return self._tracker.cancel_current()

    def get_preview(
        self, request: RefreshDailyWorkspaceRequest
    ) -> DailyWorkspaceRefreshPlan | None:
        if self._preview_daily is None:
            return None
        return self._preview_daily(request)

    def execute_generation(
        self,
        generation: int,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Run local briefing recomputation on a worker thread (backwards-compatible entrypoint)."""
        self.execute_reload_generation(
            generation,
            dispatch=dispatch,
            listener=listener,
        )

    def execute_reload_generation(
        self,
        generation: int,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Run local briefing recomputation on a worker thread."""
        try:
            response = self._load_daily()
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        status = (
            ScreenStatus.EMPTY if self._is_empty_briefing(response) else ScreenStatus.READY
        )
        dispatch(self._deliver_success, generation, response, status, listener)

    def execute_refresh_generation(
        self,
        generation: int,
        request: RefreshDailyWorkspaceRequest,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Run explicit market data refresh followed by briefing recomputation."""
        if self._refresh_daily is None:
            dispatch(
                self._deliver_failure,
                generation,
                RuntimeError("Refresh capability not configured."),
                listener,
            )
            return

        def on_start(event: Any) -> None:
            if progress_callback:
                dispatch(
                    progress_callback,
                    {
                        "type": "start",
                        "total": getattr(event, "ticker_count", 0),
                        "event": event,
                    },
                )

        def on_ticker(result: Any, index: int, total: int) -> None:
            # Matches the fetch-market workflow contract exactly:
            # on_ticker_complete(result: FetchMarketTickerResult, index, total).
            # The per-ticker result is a typed DTO, not a (ticker, status) pair;
            # derive the ticker from it and carry the whole result as status.
            if progress_callback:
                dispatch(
                    progress_callback,
                    {
                        "type": "ticker",
                        "ticker": getattr(result, "ticker", None),
                        "index": index,
                        "total": total,
                        "status": result,
                    },
                )

        try:
            result = self._refresh_daily(
                request,
                on_start=on_start,
                on_ticker_complete=on_ticker,
            )
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        status = (
            ScreenStatus.EMPTY
            if self._is_empty_briefing(result.briefing)
            else ScreenStatus.READY
        )
        dispatch(self._deliver_success, generation, result, status, listener)

    @staticmethod
    def _is_empty_briefing(response: DailyBriefingResponse) -> bool:
        setup_rows = (
            response.setup_lens_impact.rows if response.setup_lens_impact is not None else ()
        )
        return (
            response.universe_count == 0
            and response.regime is None
            and not response.opening_candidates
            and not response.market_wide_opening_observations
            and not response.accumulation_candidates
            and not response.daily_accumulation_candidates
            and not setup_rows
        )

    def _deliver_success(
        self,
        generation: int,
        payload: Any,
        status: ScreenStatus,
        listener: StateListener,
    ) -> None:
        if self._tracker.complete_current(
            generation,
            payload=payload,
            status=status,
        ):
            listener(self._tracker.state)

    def _deliver_failure(
        self,
        generation: int,
        error: Exception,
        listener: StateListener,
    ) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)
