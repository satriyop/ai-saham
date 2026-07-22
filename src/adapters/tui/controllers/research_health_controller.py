"""Generation-safe controller for one exact signal readiness report.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable

from src.adapters.tui.controllers.daily_controller import StateListener, UiDispatcher
from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.use_case.report_signal_readiness_use_case import (
    SignalReadinessReport,
)

ResearchHealthLoader = Callable[[str, str | None], SignalReadinessReport]


class ResearchHealthController:
    def __init__(self, load_report: ResearchHealthLoader) -> None:
        self._load_report = load_report
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
        target: str,
        cohort: str | None,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        try:
            if not target.strip():
                raise ValueError("target must not be blank")
            report = self._load_report(target, cohort)
            status = (
                ScreenStatus.EMPTY
                if not report.observation_dates or report.label_count == 0
                else ScreenStatus.READY
            )
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return
        dispatch(self._deliver_success, generation, report, status, listener)

    def _deliver_success(self, generation, report, status, listener) -> None:
        if self._tracker.complete_current(
            generation,
            payload=report,
            status=status,
        ):
            listener(self._tracker.state)

    def _deliver_failure(self, generation, error, listener) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)
