from __future__ import annotations

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.state import ScreenStatus

from .daily_fixtures import empty_response, partial_response, ready_response


def _immediate(callback, *args):
    callback(*args)


def test_controller_executes_exactly_one_call_and_preserves_response_identity():
    response = partial_response()
    calls = 0
    delivered = []

    def load():
        nonlocal calls
        calls += 1
        return response

    controller = DailyController(load)
    generation = controller.begin()
    controller.execute_generation(generation, dispatch=_immediate, listener=delivered.append)

    assert calls == 1
    assert controller.state.status is ScreenStatus.READY
    assert controller.state.payload is response
    assert delivered == [controller.state]


def test_controller_empty_contract_and_error_boundary_preserve_details():
    controller = DailyController(empty_response)
    generation = controller.begin()
    controller.execute_generation(generation, dispatch=_immediate, listener=lambda state: None)
    assert controller.state.status is ScreenStatus.EMPTY

    def fail():
        raise OSError("cache exploded")

    controller = DailyController(fail)
    generation = controller.begin()
    controller.execute_generation(generation, dispatch=_immediate, listener=lambda state: None)
    assert controller.state.status is ScreenStatus.ERROR
    assert controller.state.error_type == "OSError"
    assert controller.state.error_message == "cache exploded"


def test_late_first_result_cannot_replace_reload_result():
    first = ready_response()
    second = partial_response()
    responses = iter((first, second))
    queued = []
    controller = DailyController(lambda: next(responses))

    first_generation = controller.begin()
    controller.execute_generation(
        first_generation,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    second_generation = controller.begin()
    controller.execute_generation(
        second_generation,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )

    callback, args = queued[1]
    callback(*args)
    callback, args = queued[0]
    callback(*args)

    assert controller.state.generation == second_generation
    assert controller.state.payload is second
