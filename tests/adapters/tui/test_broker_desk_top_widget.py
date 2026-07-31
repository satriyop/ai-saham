"""Broker top dual-heat widget paints on hub ``t`` (Stage 3)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.broker_desk_top_model import build_broker_desk_top_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.broker_top_desk import BrokerTopDesk
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


def test_cockpit_paints_broker_top_widget_on_t():
    async def scenario() -> None:
        top_result = SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            date=date(2026, 7, 29),
            broker_type=BrokerType.FOREIGN,
            top_buy_stocks=(
                SimpleNamespace(
                    ticker="AMMN",
                    net_value=Decimal("6760000000"),
                    net_lot=500,
                ),
            ),
            top_sell_stocks=(
                SimpleNamespace(
                    ticker="BBCA",
                    net_value=Decimal("-1200000000"),
                    net_lot=-40,
                ),
            ),
            scope_note="Tracked desk",
        )
        top_model = build_broker_desk_top_model(top_result)

        def show_loader(code: str):
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

        def top_loader(code: str):
            return SimpleNamespace(
                text=f"TOP_BODY_{code}",
                model=top_model,
                jump_ticker="AMMN",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: [SimpleNamespace(code="YP", type_label="Foreign")],
            broker_show_loader=show_loader,
            broker_top_loader=top_loader,
            broker_flow_loader=lambda c: f"FLOW_{c}",
            broker_history_loader=lambda c: f"HIST_{c}",
            broker_matrix_loader=lambda c: f"MATRIX_{c}",
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

            app.action_broker_top()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "top" and app._stage == "detail":
                    break

            assert app._broker_page == "top"
            assert app._broker_desk_top_model is not None
            assert app._broker_desk_top_model.jump_ticker == "AMMN"
            assert "TOP_BODY_YP" in app._detail_text

            desk = app.query_one("#broker-top-desk", BrokerTopDesk)
            assert desk.display is True
            assert app.query_one("#broker-desk", BrokerDesk).display is False
            buy0 = str(desk.query_one("#tp-buy-0").content)
            assert "AMMN" in buy0
            sell0 = str(desk.query_one("#tp-sell-0").content)
            assert "BBCA" in sell0

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app.query_one("#broker-desk", BrokerDesk).display is True
            assert app.query_one("#broker-top-desk", BrokerTopDesk).display is False

    asyncio.run(scenario())
