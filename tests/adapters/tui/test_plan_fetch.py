"""Phase 4 — plan confirm deliberate; fetch confirm explicit."""

from __future__ import annotations

import asyncio

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.screens.fetch_confirm import FetchConfirmModal
from src.adapters.tui.screens.plan_confirm import PlanConfirmModal


def test_plan_confirm_modal_requires_enter():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            # Seed focus as if a board row was selected
            app._focus_ticker = "BBRI"
            app._stage = "accum"
            app._rows = [type("R", (), {"ticker": "BBRI"})()]
            app._row_index = 0
            planned: list[str] = []
            app._plan_runner = lambda t: planned.append(t) or type("X", (), {"summary": "ok"})()

            app._run_command("plan-swing")
            await pilot.pause()
            assert isinstance(app.screen, PlanConfirmModal)
            # Escape cancels — runner not called
            await pilot.press("escape")
            await pilot.pause()
            assert planned == []

            app._run_command("plan-swing")
            await pilot.pause()
            assert isinstance(app.screen, PlanConfirmModal)
            # Modal should echo desk vocabulary when row has fields
            body = str(app.screen.query_one("#confirm-body").render())
            assert "Signal" in body or "BBRI" in body
            # Confirm path: dismiss(True) mirrors ↵ on the modal
            app.screen.dismiss(True)
            for _ in range(50):
                await pilot.pause(0.05)
                if planned:
                    break
            assert planned == ["BBRI"]

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
