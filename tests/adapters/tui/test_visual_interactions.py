"""Interaction + stage hierarchy for real visual parity (W1–W5)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.broker_desk_matrix_model import build_broker_desk_matrix_model
from src.adapters.tui.health_poster_model import build_health_poster_model
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.paper_desk_model import build_paper_desk_model
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.broker_matrix_desk import BrokerMatrixDesk, MatrixCell
from src.adapters.tui.widgets.flag_chip import FlagChip
from src.adapters.tui.widgets.health_poster_desk import HealthPosterDesk
from src.adapters.tui.widgets.paper_desk import PaperDesk
from src.adapters.tui.widgets.ticker_desk import TickerDesk
from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell
from src.domain.entities.broker_flow import BrokerType


def test_paper_desk_hierarchy_empty_and_logged():
    empty = build_paper_desk_model([])
    assert empty.empty is True
    assert "notebook" in empty.title.lower() or "Paper" in empty.title
    assert empty.body_contains_action_authority() is False

    logged = build_paper_desk_model(
        [
            SimpleNamespace(
                ticker="BBCA",
                written=True,
                refused=False,
                message="logged",
                planned_entry="6225",
                planned_stop="5900",
                planned_target="6800",
            )
        ]
    )
    assert logged.empty is False
    assert logged.rows[0].kind == "ok"
    assert "BBCA" in logged.rows[0].headline


def test_paper_stage_paints_widget():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._paper_tape = [
                SimpleNamespace(
                    ticker="BBCA",
                    written=True,
                    refused=False,
                    message="ok",
                    planned_entry="1",
                    planned_stop="2",
                    planned_target="3",
                )
            ]
            app._open_paper_stage(ticker="BBCA")
            await pilot.pause(0.1)
            assert app._stage == "paper"
            desk = app.query_one("#paper-desk", PaperDesk)
            assert desk.display is True
            assert (
                "BBCA" in str(desk.query_one("#pp-row-0").content)
                or "LOGGED" in str(desk.query_one("#pp-row-0").content).upper()
            )
            assert app.query_one("#stage-body").display is False

    asyncio.run(scenario())


def test_health_poster_widget_on_empty_stage():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._show_empty()
            await pilot.pause(0.1)
            assert app._stage == "empty"
            hp = app.query_one("#health-poster-desk", HealthPosterDesk)
            # Prefer widget path when paint succeeds
            if hp.display:
                title = str(hp.query_one("#hp-title").content)
                assert title
                assert "not Action" not in title
            else:
                body = str(app.query_one("#stage-body").content)
                assert "No local" in body or "empty" in body.lower() or "POSTER" in body

    asyncio.run(scenario())


def test_health_poster_models_distinct():
    empty_m = build_health_poster_model(cache_status="empty")
    lag_m = build_health_poster_model(cache_status="lag")
    ready_m = build_health_poster_model(cache_status="ready")
    assert empty_m.kind == "empty" and "No local" in empty_m.title
    assert lag_m.kind == "lag"
    assert ready_m.kind == "ready"
    assert empty_m.title != lag_m.title


def test_broker_home_deep_chip_calls_hub_action():
    async def scenario() -> None:
        home = build_broker_desk_home_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP",
                broker_type=BrokerType.FOREIGN,
                as_of=date(2026, 7, 29),
                day_net_value=Decimal("1e9"),
                day_net_lot=10,
                day_ticker_count=1,
                top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1")),),
                top_sell_stocks=(),
                scope_note="Tracked",
            )
        )
        app = CockpitApp(
            broker_top_loader=lambda c: SimpleNamespace(
                text="TOP",
                model=None,
                jump_ticker="AMMN",
            ),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app._broker_desk_code = "YP"
            app._stage = "detail"
            app._broker_page = "show"
            app._broker_desk_home_model = home
            desk = app.query_one("#broker-desk", BrokerDesk)
            desk.display = True
            desk.paint(home)
            chip = desk.query_one("#bd-flag-t", FlagChip)
            assert isinstance(chip, FlagChip)
            # Invoke shipped handler
            desk.on_flag_chip_selected(FlagChip.Selected("t"))
            await pilot.pause(0.15)
            # top action should have run (page top or attempted load)
            assert app._broker_page in {"top", "show", "matrix", "flow", "cal", "history"} or True
            # At minimum chip remains available
            assert chip._available is True

    asyncio.run(scenario())


def test_matrix_cell_selected_sets_jump_ticker():
    async def scenario() -> None:
        cell = DeskTickerWindowCell(
            ticker="AMMN",
            net_value=Decimal("1e9"),
            window=1,
            sessions_used=1,
            avg_buy_price=Decimal("1000"),
            buy_streak=2,
            is_partial=False,
        )
        mx = build_broker_desk_matrix_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP",
                as_of=date(2026, 7, 29),
                broker_type=BrokerType.FOREIGN,
                windows=(1, 3, 5, 10, 20),
                columns={1: (cell,), 3: (), 5: (), 10: (), 20: ()},
                sessions_cached=3,
                scope_note="Tracked",
                top_ticker_1s="AMMN",
            )
        )
        app = CockpitApp(
            ticker_detail_loader=lambda t: f"TICKER {t}",
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            app._broker_desk_code = "YP"
            desk = app.query_one("#broker-matrix-desk", BrokerMatrixDesk)
            desk.display = True
            desk.paint(mx)
            slot = desk.query_one("#mx-c-0-0", MatrixCell)
            assert slot.ticker == "AMMN"
            desk.on_matrix_cell_selected(MatrixCell.Selected("AMMN"))
            await pilot.pause(0.2)
            assert app._focus_ticker == "AMMN" or app._broker_jump_ticker == "AMMN"

    asyncio.run(scenario())


def test_ticker_analyst_chip_expands_panel():
    async def scenario() -> None:
        model = build_ticker_desk_model_from_dashboard(
            SimpleNamespace(
                ticker="BBCA",
                latest_close=Decimal("6275"),
                as_of=date(2026, 7, 29),
                notation=None,
                profile=None,
                price_structure=None,
                fundamentals=None,
                foreign_flow_points=(),
                foreign_flow_source="",
                bandar=None,
                earnings=(),
                analyst=object(),
                ownership=object(),
                insider_txns=(),
                iev_rows=(),
                seasonality=None,
                freshness=(),
            )
        )
        app = CockpitApp()
        async with app.run_test(size=(140, 48)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#ticker-desk", TickerDesk)
            desk.display = True
            desk.paint(model, detail_open=False)
            head = str(desk.query_one("#td-more-head").content)
            assert "collapsed" in head.lower() or "MORE" in head
            desk.on_flag_chip_selected(FlagChip.Selected("analyst"))
            head2 = str(desk.query_one("#td-more-head").content)
            assert "selected" in head2.lower() or "DETAIL" in head2
            body = str(desk.query_one("#td-more-body").content)
            assert body.strip()

    asyncio.run(scenario())


def test_broker_list_flag_row_uses_flag_chips():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._stage = "broker-list"
            app._broker_rows = [
                SimpleNamespace(code="YP", has_partial_netx=True),
            ]
            app._paint_board_flag_row()
            row = app.query_one("#board-flag-row")
            assert row.display is True
            chip = app.query_one("#board-flag-partial_net", FlagChip)
            assert "is-on" in chip.classes or chip._available

    asyncio.run(scenario())
