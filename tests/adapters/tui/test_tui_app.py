"""Headless tests for the offline Daily Textual workspace."""

import asyncio

from textual.widgets import Static

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen

from .daily_fixtures import not_ready_response, ready_response


class _RecordingCapability:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.response

    def fetch(self):
        raise AssertionError("provider fake must not be called")

    def save(self):
        raise AssertionError("write fake must not be called")


async def _wait_for_calls(pilot, capability, expected):
    for _ in range(30):
        await pilot.pause(0.01)
        if capability.calls == expected:
            await pilot.pause()
            return
    raise AssertionError(f"expected {expected} Daily calls, got {capability.calls}")


def test_launch_calls_daily_once_reload_once_and_navigation_does_not_call():
    async def scenario() -> None:
        capability = _RecordingCapability(ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            assert isinstance(app.screen, DailyScreen)
            assert app.screen.query_one("#daily-title", Static).content == "Daily"
            assert "authority READY" in str(app.screen.query_one("#daily-status", Static).content)
            assert "local warning" in str(app.screen.query_one("#daily-warnings", Static).content)

            await pilot.press("?", "tab", "right", "down")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert capability.calls == 1

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyScreen)
            assert capability.calls == 1

            await pilot.press("r")
            await _wait_for_calls(pilot, capability, 2)
            assert capability.calls == 2

    asyncio.run(scenario())


def test_not_ready_is_ready_screen_output_without_usable_rankings():
    async def scenario() -> None:
        capability = _RecordingCapability(not_ready_response())
        app = create_tui_app(daily_loader=capability)
        async with app.run_test(size=(100, 32)) as pilot:
            await _wait_for_calls(pilot, capability, 1)
            assert "READY — authority NOT_READY" in str(
                app.screen.query_one("#daily-status", Static).content
            )
            assert "BBCA: flow" not in str(
                app.screen.query_one("#daily-accumulation", Static).content
            )

    asyncio.run(scenario())


def test_error_state_displays_exact_exception_class_and_message():
    def fail():
        raise ValueError("invalid local config")

    async def scenario() -> None:
        app = create_tui_app(daily_loader=fail)
        async with app.run_test(size=(100, 32)) as pilot:
            for _ in range(30):
                await pilot.pause(0.01)
                content = str(app.screen.query_one("#daily-warnings", Static).content)
                if "ValueError: invalid local config" in content:
                    break
            else:
                raise AssertionError("ERROR state was not rendered")

    asyncio.run(scenario())
