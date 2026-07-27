"""Phase 0 cockpit shell: launches, palette filters, layout chrome."""

from __future__ import annotations

import asyncio

from src.adapters.tui.composition import create_cockpit_app, create_tui_app
from src.adapters.tui.main import CockpitApp, CommandPalette


def test_create_tui_app_returns_cockpit():
    app = create_tui_app()
    assert isinstance(app, CockpitApp)
    assert create_cockpit_app is create_tui_app


def test_palette_command_catalog_includes_suggested_and_data():
    ids = {c[1] for c in CommandPalette.COMMANDS}
    assert "screen-accum" in ids
    assert "screen-preopen" in ids
    assert "plan-swing" in ids
    assert "fetch" in ids


def test_palette_filter_matches_label_and_id():
    q = "accum"
    filtered = [
        c
        for c in CommandPalette.COMMANDS
        if q in c[1].lower() or q in c[2].lower() or q in c[0].lower()
    ]
    assert any(c[1] == "screen-accum" for c in filtered)
    assert not any(c[1] == "fetch" for c in filtered)


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
            assert app._stage_name == "empty"
            stage_text = str(app.query_one("#stage").render())
            assert "No local market data" in stage_text

    asyncio.run(scenario())


def test_toggle_sidebar_binding():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            assert app._sidebar_visible is True
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app._sidebar_visible is False
            assert app.query_one("#sidebar").has_class("hidden")

    asyncio.run(scenario())
