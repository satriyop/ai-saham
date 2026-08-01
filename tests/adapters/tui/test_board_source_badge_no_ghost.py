"""Src-badge must not paint an empty bordered hollow (ghost green box)."""

from __future__ import annotations

import asyncio

from textual.widgets import Static

from src.adapters.tui.main import CockpitApp


def test_hidden_badge_has_hide_class_and_no_layout():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.05)
            badge = app.query_one("#board-source-badge", Static)
            # Before / off accum: hide class + display false
            app._stage = "shell"
            app._paint_board_source_badge()
            await pilot.pause(0.02)
            assert "hide" in badge.classes
            assert badge.display is False
            assert badge.region.width == 0 or badge.size.width == 0

            # Live accum with text: visible, live class, not hide
            app._stage = "accum"
            app._board_source = "live"
            app._recomputing = False
            app._paint_board_source_badge()
            await pilot.pause(0.02)
            assert "hide" not in badge.classes
            assert "live" in badge.classes
            assert badge.display is True
            rendered = badge.render()
            plain = rendered.plain if hasattr(rendered, "plain") else str(rendered)
            assert "live" in plain.lower()

            # Back to non-accum: hollow must not remain
            app._stage = "detail"
            app._paint_board_source_badge()
            await pilot.pause(0.02)
            assert "hide" in badge.classes
            assert "live" not in badge.classes
            assert badge.display is False

    asyncio.run(scenario())
