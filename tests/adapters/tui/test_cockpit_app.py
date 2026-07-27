"""Cockpit shell + palette + empty (Phases 0–1)."""

from __future__ import annotations

import asyncio

from src.adapters.tui.commands import filter_commands
from src.adapters.tui.composition import create_cockpit_app, create_tui_app
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.screens.help import HelpModal
from src.adapters.tui.screens.palette import CommandPalette


def test_create_tui_app_returns_cockpit():
    app = create_tui_app()
    assert isinstance(app, CockpitApp)
    assert create_cockpit_app is create_tui_app


def test_filter_commands_matches_accum():
    hits = filter_commands("accum")
    assert any(c.command_id == "screen-accum" for c in hits)
    assert not any(c.command_id == "fetch" for c in hits)


def test_filter_commands_empty_returns_all():
    assert len(filter_commands("")) >= 8


def test_cockpit_mounts_layout_b_and_opens_palette():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            assert app.query_one("#main")
            assert app.query_one("#sidebar")
            assert app.query_one("#status")
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, CommandPalette)

    asyncio.run(scenario())


def test_empty_cache_command_switches_stage():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._run_command("empty-demo")
            await pilot.pause()
            assert app._stage == "empty"
            stage_text = str(app.query_one("#stage-body").render())
            assert "No local market data" in stage_text

    asyncio.run(scenario())


def test_toggle_sidebar_and_help():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app._sidebar_visible is False
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario())


def test_plan_blocked_when_empty():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._run_command("empty-demo")
            await pilot.pause()
            app._run_command("plan-swing")
            await pilot.pause()
            # Still empty — plan modal must not open without focus
            assert app._stage == "empty"
            assert not type(app.screen).__name__.endswith("PlanConfirmModal")

    asyncio.run(scenario())


def test_supported_terminal_sizes_mount():
    """Phase 5: 80x24 navigable shell; 120x40 reference layout."""

    async def scenario(size: tuple[int, int]) -> None:
        app = CockpitApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#main")
            assert app.query_one("#status")
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario((80, 24)))
    asyncio.run(scenario((120, 40)))
