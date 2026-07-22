"""Headless tests for the minimal 80x24 Textual shell."""

import asyncio

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.screens.daily import DailyShellScreen
from src.adapters.tui.screens.help import HelpScreen


def test_shell_launches_navigates_help_and_exits_offline():
    async def scenario() -> None:
        app = create_tui_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DailyShellScreen)
            assert app.screen.query_one("#daily-title").content == "Daily"

            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert app.screen.query_one("#help-title").content == "Help"

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyShellScreen)

            await pilot.press("q")

    asyncio.run(scenario())


def test_focus_cursor_and_route_navigation_have_no_application_capability():
    async def scenario() -> None:
        app = create_tui_app()
        assert not hasattr(app, "daily_use_case")
        assert not hasattr(app, "application_capability")

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("tab", "right", "down", "h", "escape")
            await pilot.pause()
            assert isinstance(app.screen, DailyShellScreen)

    asyncio.run(scenario())
