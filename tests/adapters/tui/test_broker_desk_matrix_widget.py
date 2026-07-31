"""Broker matrix desk widget paints structured model (Stage 2)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_matrix_model import build_broker_desk_matrix_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.broker_matrix_desk import BrokerMatrixDesk
from src.application.services.broker_desk_from_daily_flow import DeskTickerWindowCell
from src.domain.entities.broker_flow import BrokerType


def _accum_payload():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=50.0,
        signal_assessment=None,
        trade_setup=None,
        risk_assessment=None,
        setup_phase=None,
        consecutive_streak=1,
        rsi=50,
        net_buy_ratio=0.5,
        vwap_discount_pct=1.0,
        current_price=1000,
        name="BBCA",
    )
    return SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        effective_session=None,
        market_context=None,
        multi_projection=None,
        warnings=(),
    )


def test_cockpit_paints_broker_matrix_widget_on_m():
    async def scenario() -> None:
        cell = DeskTickerWindowCell(
            ticker="AMMN",
            net_value=Decimal("6760000000"),
            window=1,
            sessions_used=1,
            avg_buy_price=Decimal("9850"),
            buy_streak=6,
            is_partial=False,
        )
        result = SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            as_of=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            windows=(1, 3, 5, 10, 20),
            columns={1: (cell,), 3: (), 5: (), 10: (), 20: ()},
            sessions_cached=7,
            scope_note="Tracked desk",
            top_ticker_1s="AMMN",
        )
        mx_model = build_broker_desk_matrix_model(result)

        def show_loader(code: str):
            from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model

            home = build_broker_desk_home_model(
                SimpleNamespace(
                    broker_code=code,
                    broker_name="YP Desk",
                    broker_type=BrokerType.FOREIGN,
                    as_of=date(2026, 7, 29),
                    day_net_value=Decimal("1000000000"),
                    day_net_lot=100,
                    day_ticker_count=1,
                    top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1")),),
                    top_sell_stocks=(),
                    scope_note="Tracked",
                )
            )
            return SimpleNamespace(text=f"SHOW_{code}", jump_ticker="AMMN", model=home)

        def matrix_loader(code: str):
            return SimpleNamespace(
                text=f"MATRIX_BODY_{code}",
                model=mx_model,
                jump_ticker="AMMN",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: [SimpleNamespace(code="YP", type_label="Foreign")],
            broker_show_loader=show_loader,
            broker_matrix_loader=matrix_loader,
            broker_top_loader=lambda c: f"TOP_{c}",
            broker_flow_loader=lambda c: f"FLOW_{c}",
            broker_history_loader=lambda c: f"HIST_{c}",
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break

            app._run_command("view-broker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break

            app._open_broker_desk_show()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._broker_page == "show":
                    break
            assert app.query_one("#broker-desk", BrokerDesk).display is True

            app.action_broker_matrix()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "matrix" and app._stage == "detail":
                    break

            assert app._broker_page == "matrix"
            assert app._broker_desk_matrix_model is not None
            assert app._broker_desk_matrix_model.jump_ticker == "AMMN"
            assert "MATRIX_BODY_YP" in app._detail_text

            mx = app.query_one("#broker-matrix-desk", BrokerMatrixDesk)
            assert mx.display is True
            assert app.query_one("#broker-desk", BrokerDesk).display is False
            cell0 = str(mx.query_one("#mx-c-0-0").content)
            assert "AMMN" in cell0
            assert "6s" in cell0
            assert "@ 9,850" in cell0 or "9,850" in cell0

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app.query_one("#broker-desk", BrokerDesk).display is True
            assert app.query_one("#broker-matrix-desk", BrokerMatrixDesk).display is False

    asyncio.run(scenario())
