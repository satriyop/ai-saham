"""Plan stage (no modal) + fetch confirm explicit."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.screens.fetch_confirm import FetchConfirmModal


def test_plan_stage_auto_runs_without_modal():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._focus_ticker = "BBRI"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBRI",
                    signal="72",
                    accum="50.0",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            planned: list[str] = []
            app._plan_runner = (
                lambda t: planned.append(t) or type("X", (), {"summary": "local WATCH · ok"})()
            )

            app._run_command("plan-swing")
            await pilot.pause()
            # No modal — main stage is plan
            assert app._stage == "plan"
            assert not type(app.screen).__name__.endswith("PlanConfirmModal")
            assert "Plan · BBRI" in app._board_title

            for _ in range(50):
                await pilot.pause(0.05)
                if planned and not app._plan_running:
                    break
            assert planned == ["BBRI"]
            assert app._stage == "plan"  # stay on plan page with result
            assert "local WATCH" in app._plan_result or "ok" in app._plan_result
            body = app._plan_body_text()
            assert "No broker order" in body
            assert "WATCH" in body or "BBRI" in body

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_fetch_confirm_opens_and_cancels():
    async def scenario() -> None:
        app = CockpitApp(
            fetch_previewer=lambda: type("P", (), {"summary": "preview 10 tickers"})(),
            fetch_runner=lambda: (_ for _ in ()).throw(AssertionError("must not run")),
        )
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._run_command("fetch")
            await pilot.pause()
            assert isinstance(app.screen, FetchConfirmModal)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, FetchConfirmModal)

    asyncio.run(scenario())
