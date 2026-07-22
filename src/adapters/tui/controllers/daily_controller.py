"""Generation-safe controller for one offline Daily briefing capability.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable

from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse

DailyLoader = Callable[[], DailyBriefingResponse]
StateListener = Callable[[ScreenState], None]
UiDispatcher = Callable[..., object]


class DailyController:
    """Invoke exactly one injected Daily capability per explicit generation."""

    def __init__(self, load_daily: DailyLoader) -> None:
        self._load_daily = load_daily
        self._tracker = ScreenStateTracker()

    @property
    def state(self) -> ScreenState:
        return self._tracker.state

    def begin(self) -> int:
        return self._tracker.begin()

    def cancel_current(self) -> bool:
        return self._tracker.cancel_current()

    def execute_generation(
        self,
        generation: int,
        *,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        """Run on a worker thread and dispatch one terminal delivery to the UI."""
        try:
            response = self._load_daily()
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return

        status = ScreenStatus.EMPTY if self._is_empty_response(response) else ScreenStatus.READY
        dispatch(self._deliver_success, generation, response, status, listener)

    @staticmethod
    def _is_empty_response(response: DailyBriefingResponse) -> bool:
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
        response: DailyBriefingResponse,
        status: ScreenStatus,
        listener: StateListener,
    ) -> None:
        if self._tracker.complete_current(
            generation,
            payload=response,
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
