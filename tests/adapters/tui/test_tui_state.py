"""Tests for generation-safe TUI screen state."""

import pytest

from src.adapters.tui.state import ScreenState, ScreenStateTracker, ScreenStatus


@pytest.mark.parametrize(
    "state",
    [
        lambda: ScreenState(generation=-1, status=ScreenStatus.IDLE),
        lambda: ScreenState(generation=0, status=ScreenStatus.READY),
        lambda: ScreenState(generation=0, status=ScreenStatus.ERROR),
        lambda: ScreenState(
            generation=0,
            status=ScreenStatus.ERROR,
            error_type="RuntimeError",
        ),
        lambda: ScreenState(
            generation=0,
            status=ScreenStatus.IDLE,
            error_type="RuntimeError",
            error_message="failed",
        ),
    ],
)
def test_invalid_screen_state_combinations_fail(state):
    with pytest.raises(ValueError):
        state()


def test_begin_is_monotonic_and_enters_loading():
    tracker = ScreenStateTracker()

    first = tracker.begin()
    second = tracker.begin()

    assert first == 1
    assert second == 2
    assert tracker.state == ScreenState(generation=2, status=ScreenStatus.LOADING)


def test_stale_completion_cannot_replace_newer_state_and_payload_identity_is_preserved():
    tracker = ScreenStateTracker()
    stale_generation = tracker.begin()
    current_generation = tracker.begin()
    stale_payload = object()
    current_payload = object()

    assert tracker.complete_current(stale_generation, payload=stale_payload) is False
    assert tracker.state.status is ScreenStatus.LOADING
    assert tracker.complete_current(current_generation, payload=current_payload) is True
    assert tracker.state.status is ScreenStatus.READY
    assert tracker.state.payload is current_payload


def test_stale_failure_is_ignored_and_current_failure_retains_class_and_message():
    tracker = ScreenStateTracker()
    stale_generation = tracker.begin()
    current_generation = tracker.begin()
    failure = RuntimeError("worker failed")

    assert tracker.fail_current(stale_generation, ValueError("stale")) is False
    assert tracker.fail_current(current_generation, failure) is True
    assert tracker.state == ScreenState(
        generation=current_generation,
        status=ScreenStatus.ERROR,
        error_type="RuntimeError",
        error_message="worker failed",
    )
    assert tracker.fail_current(current_generation, RuntimeError("late")) is False


@pytest.mark.parametrize("status", [ScreenStatus.EMPTY, ScreenStatus.UNAVAILABLE])
def test_valid_non_ready_completion_can_retain_source_payload(status):
    tracker = ScreenStateTracker()
    generation = tracker.begin()
    source_payload = object()

    assert tracker.complete_current(
        generation,
        payload=source_payload,
        status=status,
    )
    assert tracker.state.payload is source_payload
    assert tracker.state.status is status


def test_invalid_current_completion_status_fails():
    tracker = ScreenStateTracker()
    generation = tracker.begin()

    with pytest.raises(ValueError, match="completion status"):
        tracker.complete_current(
            generation,
            payload=object(),
            status=ScreenStatus.ERROR,
        )
