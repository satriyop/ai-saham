"""Generation-safe local-only ticker research controller.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.adapters.tui.controllers.daily_controller import StateListener, UiDispatcher
from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.dto.swing_analysis import SwingAnalysisWorkflowResponse
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
)

TickerLoader = Callable[[str], SwingAnalysisWorkflowResponse]


@dataclass(frozen=True)
class TickerUnavailable:
    ticker: str
    reason: str


class TickerResearchController:
    def __init__(self, load_ticker: TickerLoader) -> None:
        self._load_ticker = load_ticker
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
        ticker: str,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        try:
            response = self._load_ticker(ticker)
            if response.ticker != ticker:
                raise ValueError(
                    f"ticker response identity mismatch: requested {ticker!r}, "
                    f"received {response.ticker!r}"
                )
        except SwingAnalysisDataUnavailable as exc:
            dispatch(
                self._deliver_unavailable,
                generation,
                TickerUnavailable(exc.ticker, str(exc)),
                listener,
            )
            return
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return
        dispatch(self._deliver_success, generation, response, listener)

    def _deliver_success(self, generation, response, listener) -> None:
        if self._tracker.complete_current(generation, payload=response):
            listener(self._tracker.state)

    def _deliver_unavailable(self, generation, unavailable, listener) -> None:
        if self._tracker.complete_current(
            generation,
            payload=unavailable,
            status=ScreenStatus.UNAVAILABLE,
        ):
            listener(self._tracker.state)

    def _deliver_failure(self, generation, error, listener) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)
