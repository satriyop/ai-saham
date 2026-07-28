"""Plan stage (structure desk, no modal) + fetch confirm explicit."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.plan_stage_presenter import present_plan_stage
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
            app._plan_runner = lambda t: (
                planned.append(t)
                or type(
                    "X",
                    (),
                    {
                        "summary": (
                            "structure WATCH · entry 4,825 · stop 4,600 · "
                            "target 5,275 · 2 lots · no order"
                        )
                    },
                )()
            )

            app._run_command("plan-swing")
            await pilot.pause()
            # No modal — main stage is plan structure desk
            assert app._stage == "plan"
            assert not type(app.screen).__name__.endswith("PlanConfirmModal")
            assert "Plan · BBRI" in app._board_title
            assert "structure" in app._board_title.lower() or "Plan" in app._board_title

            for _ in range(50):
                await pilot.pause(0.05)
                if planned and not app._plan_running:
                    break
            assert planned == ["BBRI"]
            assert app._stage == "plan"  # stay on plan page with result
            assert "structure" in app._plan_result.lower()
            assert "no order" in app._plan_result.lower()
            body = app._plan_body_text()
            assert "Structure desk" in body or "structure" in body.lower()
            assert "No broker order" in body or "no broker order" in body.lower()
            assert "WATCH" in body or "BBRI" in body
            assert "re-check" not in body.lower()
            assert "re-score" not in body.lower()

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_plan_stage_presenter_is_structure_desk_not_rescore():
    view = present_plan_stage(
        SimpleNamespace(
            ticker="BBCA",
            signal="73",
            accum="61",
            action="ENTER",
            gate="OPEN",
            source=None,
        ),
        ticker="BBCA",
        source="Screen · accumulation",
        result_line="structure ENTER · entry 6,225 · 3 lots · no order",
        running=False,
    )
    text = view.text.lower()
    assert "structure" in text
    assert "re-check" not in text
    assert "screen-accum path" not in text
    assert "enter" in text
    assert "no broker order" in text


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
