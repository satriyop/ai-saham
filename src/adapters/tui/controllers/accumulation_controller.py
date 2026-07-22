"""Generation-safe controller for the canonical accumulation projection.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.adapters.tui.controllers.daily_controller import StateListener, UiDispatcher
from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowResult,
    ScreenAccumMultiProjection,
    ScreenAccumSingleProjection,
)

AccumulationLoader = Callable[[bool], RunAccumulationScreenWorkflowResult]
AccumulationProjection = ScreenAccumSingleProjection | ScreenAccumMultiProjection


@dataclass(frozen=True)
class AccumulationControllerPayload:
    result: RunAccumulationScreenWorkflowResult
    projection: AccumulationProjection
    multi: bool

    def __post_init__(self) -> None:
        expected = self.result.multi_projection if self.multi else self.result.single_projection
        other = self.result.single_projection if self.multi else self.result.multi_projection
        if expected is None or other is not None:
            raise ValueError("accumulation result must contain exactly one requested projection")
        if self.projection is not expected:
            raise ValueError("accumulation projection identity was not preserved")


class AccumulationController:
    def __init__(self, load_accumulation: AccumulationLoader) -> None:
        self._load_accumulation = load_accumulation
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
        multi: bool,
        dispatch: UiDispatcher,
        listener: StateListener,
    ) -> None:
        try:
            result = self._load_accumulation(multi)
            projection = result.multi_projection if multi else result.single_projection
            if projection is None:
                raise ValueError("accumulation workflow omitted the requested projection")
            payload = AccumulationControllerPayload(result, projection, multi)
            rows = projection.rows if multi else projection.candidates
            status = ScreenStatus.EMPTY if not rows else ScreenStatus.READY
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return
        dispatch(self._deliver_success, generation, payload, status, listener)

    def _deliver_success(self, generation, payload, status, listener) -> None:
        if self._tracker.complete_current(generation, payload=payload, status=status):
            listener(self._tracker.state)

    def _deliver_failure(self, generation, error, listener) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)
