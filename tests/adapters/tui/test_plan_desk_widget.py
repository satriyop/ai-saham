"""Plan desk Geometry-mast widget — design-aligned, present-only structure."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.main import CockpitApp
from src.adapters.tui.plan_desk_model import build_plan_desk_model
from src.adapters.tui.plan_structure_result import PlanStructureResult
from src.adapters.tui.widgets.plan_desk import PlanDesk


def test_build_plan_desk_model_geometry_and_inherit():
    row = SimpleNamespace(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        gate="OPEN",
        source=None,
    )
    struct = PlanStructureResult(
        summary="structure WATCH · entry 6,225 · stop 5,900 · target 6,800 · 3 lots · no order",
        ticker="BBCA",
        action="WATCH",
        entry="6,225",
        stop="5,900",
        target="6,800",
        lots="3",
        plan_id_short="3f88eda7",
        risk_pct="1.0",
        horizon="swing",
        inherits_action=True,
        no_order=True,
    )
    model = build_plan_desk_model(
        row,
        ticker="BBCA",
        source="Screen · accumulation",
        rank=2,
        total=20,
        structure=struct,
        running=False,
    )
    assert model.action == "WATCH"
    assert model.entry == "6,225"
    assert model.stop == "5,900"
    assert model.target == "6,800"
    assert model.lots == "3"
    assert model.has_geometry is True
    assert model.no_order is True
    assert "re-score" in model.inherit_note.lower() or "inherit" in model.inherit_note.lower()
    keys = {c.key for c in model.cards}
    assert "board" in keys
    assert "sizing" in keys
    assert "status" in keys
    board = next(c for c in model.cards if c.key == "board")
    assert "84" in "\n".join(board.lines) or "Signal" in board.headline


def test_build_plan_desk_model_incomplete_capital():
    model = build_plan_desk_model(
        None,
        ticker="ASII",
        structure=PlanStructureResult(
            summary="structure WATCH · no capital · no order",
            action="WATCH",
            incomplete_reason="no capital · set swing.capital",
            inherits_action=True,
            no_order=True,
        ),
    )
    assert model.has_geometry is False
    status = next(c for c in model.cards if c.key == "status")
    assert "capital" in "\n".join(status.lines).lower() or "cannot" in status.headline.lower()


def test_cockpit_paints_plan_desk_geometry_mast():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBCA"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBCA",
                    signal="84",
                    accum="48.2",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0

            def runner(t: str) -> PlanStructureResult:
                return PlanStructureResult(
                    summary=(
                        "structure WATCH · entry 6,225 · stop 5,900 · "
                        "target 6,800 · 3 lots · no order"
                    ),
                    ticker=t,
                    action="WATCH",
                    entry="6,225",
                    stop="5,900",
                    target="6,800",
                    lots="3",
                    plan_id_short="3f88eda7",
                    risk_pct="1.0",
                    inherits_action=True,
                    no_order=True,
                )

            app._plan_runner = runner
            app._run_command("plan-swing")
            for _ in range(50):
                await pilot.pause(0.05)
                if not app._plan_running and app._plan_structure is not None:
                    break

            assert app._stage == "plan"
            desk = app.query_one("#plan-desk", PlanDesk)
            assert desk.display is True
            entry = str(app.query_one("#pd-entry").render())
            stop = str(app.query_one("#pd-stop").render())
            target = str(app.query_one("#pd-target").render())
            assert "6,225" in entry
            assert "5,900" in stop
            assert "6,800" in target
            action = str(app.query_one("#pd-action").render())
            assert "WATCH" in action
            no_order = str(app.query_one("#pd-no-order").render()).lower()
            assert "no broker order" in no_order
            # Text presenter still available for scrapers
            body = app._plan_body_text()
            assert "6,225" in body and "structure" in body.lower()

            await pilot.press("escape")
            await pilot.pause(0.05)
            assert app._stage == "accum"
            assert desk.display is False

    asyncio.run(scenario())
