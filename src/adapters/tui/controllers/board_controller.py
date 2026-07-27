"""Generic generation-safe board loader controller.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus

StateListener = Callable[[ScreenState], None]
UiDispatcher = Callable[..., object]
BoardLoader = Callable[[], Any]


class BoardController:
    """Run one injected loader per generation; EMPTY when payload is empty list/None."""

    def __init__(self, loader: BoardLoader, *, empty_when: Callable[[Any], bool] | None = None):
        self._loader = loader
        self._empty_when = empty_when or _default_empty
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
        try:
            payload = self._loader()
            if self._empty_when(payload):
                status = ScreenStatus.EMPTY
                payload_out: Any | None = payload
            else:
                status = ScreenStatus.READY
                payload_out = payload
        except Exception as exc:
            dispatch(self._deliver_failure, generation, exc, listener)
            return
        dispatch(self._deliver_success, generation, payload_out, status, listener)

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
        error: BaseException,
        listener: StateListener,
    ) -> None:
        if self._tracker.fail_current(generation, error):
            listener(self._tracker.state)


def _default_empty(payload: Any) -> bool:
    if payload is None:
        return True
    rows = getattr(payload, "rows", None)
    if rows is not None:
        return len(rows) == 0
    if isinstance(payload, (list, tuple)):
        return len(payload) == 0
    return False
