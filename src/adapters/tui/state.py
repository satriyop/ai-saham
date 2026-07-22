"""Adapter-only screen state and request-generation tracking.

The tracker is intentionally independent of Textual. A screen controller may
begin a generation before starting one thread worker, then deliver the result
back on Textual's UI thread through ``App.call_from_thread``. Late results are
ignored by generation rather than being allowed to replace newer state.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScreenStatus(StrEnum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    READY = "READY"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ScreenState:
    generation: int
    status: ScreenStatus
    payload: object | None = None
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.generation < 0:
            raise ValueError("generation must not be negative")
        if self.status is ScreenStatus.READY and self.payload is None:
            raise ValueError("READY state requires a payload")
        if self.status is ScreenStatus.ERROR:
            if self.error_type is None or self.error_message is None:
                raise ValueError("ERROR state requires error_type and error_message")
        elif self.error_type is not None or self.error_message is not None:
            raise ValueError("non-ERROR state must not contain error fields")


class ScreenStateTracker:
    """Monotonic state holder that rejects stale worker delivery."""

    _COMPLETION_STATUSES = frozenset(
        {ScreenStatus.READY, ScreenStatus.EMPTY, ScreenStatus.UNAVAILABLE}
    )

    def __init__(self) -> None:
        self._state = ScreenState(generation=0, status=ScreenStatus.IDLE)

    @property
    def state(self) -> ScreenState:
        return self._state

    def begin(self) -> int:
        generation = self._state.generation + 1
        self._state = ScreenState(
            generation=generation,
            status=ScreenStatus.LOADING,
        )
        return generation

    def cancel_current(self) -> bool:
        """Invalidate one loading generation without fabricating a result."""
        if self._state.status is not ScreenStatus.LOADING:
            return False
        self._state = ScreenState(
            generation=self._state.generation + 1,
            status=ScreenStatus.IDLE,
        )
        return True

    def complete_current(
        self,
        generation: int,
        *,
        payload: object | None,
        status: ScreenStatus = ScreenStatus.READY,
    ) -> bool:
        if generation != self._state.generation or self._state.status is not ScreenStatus.LOADING:
            return False
        if status not in self._COMPLETION_STATUSES:
            raise ValueError("completion status must be READY, EMPTY, or UNAVAILABLE")
        self._state = ScreenState(
            generation=generation,
            status=status,
            payload=payload,
        )
        return True

    def fail_current(self, generation: int, error: BaseException) -> bool:
        if generation != self._state.generation or self._state.status is not ScreenStatus.LOADING:
            return False
        self._state = ScreenState(
            generation=generation,
            status=ScreenStatus.ERROR,
            error_type=type(error).__name__,
            error_message=str(error),
        )
        return True
