"""Phase 5 release-gate tests for the complete read-only TUI journey."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import Event, Lock

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Static

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.screens.screen_workspace_screen import ScreenWorkspaceScreen
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen
from src.adapters.tui.screens.ticker_workbench_screen import TickerWorkbenchScreen

from .daily_fixtures import (
    empty_response,
    not_ready_response,
    partial_response,
    ready_response,
)
from .research_fixtures import single_result, ticker_response


async def _wait_until(pilot, predicate, message: str) -> None:
    for _ in range(100):
        await pilot.pause(0.01)
        if predicate():
            await pilot.pause()
            return
    raise AssertionError(message)


class _StrictJourneyCapabilities:
    def __init__(self) -> None:
        self.daily_calls = 0
        self.accumulation_calls: list[bool] = []
        self.ticker_calls: list[str] = []

    def daily(self):
        self.daily_calls += 1
        return ready_response()

    def accumulation(self, request):
        self.accumulation_calls.append(request.multi)
        return single_result()

    def ticker(self, ticker: str, mode=None, setup=None):
        self.ticker_calls.append(ticker)
        return ticker_response(ticker=ticker)

    def fetch(self):
        raise AssertionError("network/provider call forbidden")

    def save(self):
        raise AssertionError("business write forbidden")


@pytest.mark.parametrize(
    ("response_factory", "authority"),
    [
        (ready_response, "READY"),
        (partial_response, "PARTIAL"),
        (not_ready_response, "NOT_READY"),
    ],
)
def test_daily_authority_is_textual_for_every_canonical_state(response_factory, authority):
    async def scenario() -> None:
        app = create_tui_app(daily_loader=response_factory)
        async with app.run_test(size=(80, 24)) as pilot:
            await _wait_until(
                pilot,
                lambda: authority in str(app.screen.query_one("#daily-status", Static).content),
                f"Daily did not render {authority}",
            )
            assert authority in str(app.screen.query_one("#daily-readiness", Static).content)

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(80, 24), (120, 40), (160, 50)])
def test_full_keyboard_journey_is_offline_read_only_and_authority_safe(size):
    async def scenario() -> None:
        capabilities = _StrictJourneyCapabilities()
        app = create_tui_app(
            daily_loader=capabilities.daily,
            accumulation_loader=capabilities.accumulation,
            ticker_loader=capabilities.ticker,
        )
        assert not hasattr(app, "action_show_research")
        assert all(binding.key != "3" for binding in app.BINDINGS)
        async with app.run_test(size=size) as pilot:
            await _wait_until(
                pilot,
                lambda: capabilities.daily_calls == 1,
                "Daily did not load",
            )
            assert isinstance(app.screen, DailyScreen)
            assert "OFFLINE" in app.sub_title

            await pilot.press("2")
            await _wait_until(
                pilot,
                lambda: capabilities.accumulation_calls == [False],
                "Candidates did not load",
            )
            assert isinstance(app.screen, ScreenWorkspaceScreen)
            selected = str(app.screen.query_one("#candidate-selected", Static).content)
            assert "Action: WATCH" in selected
            assert "Risk: OPEN" in selected
            assert "Data: ALIGNED" in selected

            # Enter opens the workbench; analysis must not run on mount.
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, TickerWorkbenchScreen)
            assert capabilities.ticker_calls == []

            # Default mode is Cached only — an explicit Run stays offline.
            await pilot.press("r")
            await _wait_until(
                pilot,
                lambda: capabilities.ticker_calls == ["BBRI"],
                "Ticker analysis did not load",
            )
            verdict = str(app.screen.query_one("#wb-verdict", Static).content)
            assert "CANONICAL_ONLY" in verdict
            assert "PREVIEW_ONLY" not in verdict
            await pilot.click("#wb-tab-signal_risk")
            await pilot.pause()
            body = str(app.screen.query_one("#wb-tab-body", Static).content)
            assert "NON-CANONICAL PREVIEW" in body
            assert "PREVIEW_ONLY" in body

            await pilot.press("escape", "escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)
            assert app.title == "AI Saham · Today"
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            help_copy = "\n".join(
                str(widget.content) for widget in app.screen.query(Static)
            )
            assert "Research" not in help_copy
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)

        assert capabilities.daily_calls == 1
        assert capabilities.accumulation_calls == [False]
        assert capabilities.ticker_calls == ["BBRI"]

    asyncio.run(scenario())


def test_80x24_warnings_are_keyboard_reachable_and_large_layout_is_wide():
    async def scenario() -> None:
        app = create_tui_app(daily_loader=ready_response)
        async with app.run_test(size=(80, 24)) as pilot:
            await _wait_until(
                pilot,
                lambda: (
                    "local warning" in str(app.screen.query_one("#daily-warnings", Static).content)
                ),
                "Daily warning did not render",
            )
            content = app.screen.query_one("#daily-content", VerticalScroll)
            content.focus()
            await pilot.press("end")
            await pilot.pause()
            assert content.scroll_y > 0
            assert "local warning" in str(app.screen.query_one("#daily-warnings", Static).content)

            await pilot.resize_terminal(160, 50)
            await pilot.press("2")
            await _wait_until(
                pilot,
                lambda: (
                    isinstance(app.screen, ScreenWorkspaceScreen) and app.screen.has_class("wide")
                ),
                "Candidate browser did not enter wide layout",
            )

    asyncio.run(scenario())


def test_empty_daily_and_candidate_states_keep_navigation_available():
    result = single_result()
    empty_projection = replace(
        result.single_projection,
        candidates=[],
        raw_candidate_count=0,
        projected_candidate_count=0,
    )
    empty_candidates = replace(result, single_projection=empty_projection)

    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=empty_response,
            accumulation_loader=lambda request: empty_candidates,
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await _wait_until(
                pilot,
                lambda: "EMPTY" in str(app.screen.query_one("#daily-status", Static).content),
                "Daily EMPTY did not render",
            )
            await pilot.press("2")
            await _wait_until(
                pilot,
                lambda: (
                    isinstance(app.screen, ScreenWorkspaceScreen)
                    and "EMPTY" in str(app.screen.query_one("#candidate-status", Static).content)
                ),
                "Candidate EMPTY did not render",
            )
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)

    asyncio.run(scenario())


def test_error_allows_explicit_reload_recovery_without_automatic_retry():
    calls = 0

    def load_daily():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("controlled local failure")
        return ready_response()

    async def scenario() -> None:
        app = create_tui_app(daily_loader=load_daily)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_until(
                pilot,
                lambda: (
                    "controlled local failure"
                    in str(app.screen.query_one("#daily-warnings", Static).content)
                ),
                "Daily error did not render",
            )
            assert calls == 1
            await pilot.pause(0.05)
            assert calls == 1
            await pilot.press("r")
            await _wait_until(
                pilot,
                lambda: (
                    calls == 2
                    and "authority READY"
                    in str(app.screen.query_one("#daily-status", Static).content)
                ),
                "Daily retry did not recover",
            )

    asyncio.run(scenario())


def test_route_switch_cancels_late_result_before_hidden_ui_mutation():
    started = Event()
    release = Event()

    def delayed_daily():
        started.set()
        release.wait(3)
        return ready_response()

    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=delayed_daily,
            accumulation_loader=lambda request: single_result(),
        )
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_until(pilot, started.is_set, "Daily worker did not start")
            daily_screen = app.screen
            await pilot.press("2")
            await _wait_until(
                pilot,
                lambda: isinstance(app.screen, ScreenWorkspaceScreen),
                "Candidate route did not open",
            )
            assert "cancelled" in str(daily_screen.query_one("#daily-status", Static).content)
            release.set()
            await pilot.pause(0.1)
            assert isinstance(app.screen, ScreenWorkspaceScreen)
            assert "authority READY" not in str(
                daily_screen.query_one("#daily-status", Static).content
            )

    asyncio.run(scenario())


def test_out_of_order_reload_and_exit_during_work_are_safe():
    started = [Event(), Event(), Event()]
    release = [Event(), Event(), Event()]
    lock = Lock()
    call_index = 0

    def delayed_daily():
        nonlocal call_index
        with lock:
            index = call_index
            call_index += 1
        started[index].set()
        release[index].wait(3)
        return partial_response() if index == 1 else ready_response()

    async def scenario() -> None:
        loop_errors = []
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda current_loop, context: loop_errors.append(context))
        try:
            app = create_tui_app(daily_loader=delayed_daily)
            async with app.run_test(size=(100, 32)) as pilot:
                await _wait_until(pilot, started[0].is_set, "First worker did not start")
                await pilot.press("r")
                await _wait_until(pilot, started[1].is_set, "Reload worker did not start")
                release[1].set()
                await _wait_until(
                    pilot,
                    lambda: (
                        "authority PARTIAL"
                        in str(app.screen.query_one("#daily-status", Static).content)
                    ),
                    "Newer reload did not render",
                )
                release[0].set()
                await pilot.pause(0.1)
                assert "authority PARTIAL" in str(
                    app.screen.query_one("#daily-status", Static).content
                )

                await pilot.press("r")
                await _wait_until(pilot, started[2].is_set, "Exit worker did not start")
                await pilot.press("q")
                release[2].set()
                await pilot.pause(0.05)
            await asyncio.sleep(0.05)
            assert loop_errors == []
        finally:
            release[0].set()
            release[1].set()
            release[2].set()
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())
