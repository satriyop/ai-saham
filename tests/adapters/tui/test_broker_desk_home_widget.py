"""Broker desk-home widget paints structured model (Stage 1)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_desk import BrokerDesk
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


def test_cockpit_paints_broker_desk_home_widget():
    async def scenario() -> None:
        show_result = SimpleNamespace(
            broker_code="YP",
            broker_name="YP Desk",
            broker_type=BrokerType.FOREIGN,
            as_of=date(2026, 7, 29),
            day_net_value=Decimal("11460000000"),
            day_net_lot=413768,
            day_ticker_count=45,
            top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("6760000000")),),
            top_sell_stocks=(),
            scope_note="Tracked desk activity only (broker_daily_flow)",
        )
        pulse = SimpleNamespace(
            day_net=Decimal("11460000000"),
            net5=Decimal("38200000000"),
            sessions_in_net5=5,
            buy_streak=4,
            delta1=Decimal("2100000000"),
        )
        model = build_broker_desk_home_model(show_result, pulse=pulse)

        def show_loader(code: str):
            return SimpleNamespace(
                text=f"SHOW_BODY_{code}",
                jump_ticker="AMMN",
                model=model,
            )

        pages: list[str] = []

        def matrix_loader(code: str) -> str:
            pages.append("matrix")
            return f"MATRIX_{code}"

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

            assert app._broker_page == "show"
            assert app._broker_desk_home_model is not None
            assert app._broker_desk_home_model.day_net_amount
            assert "11.46" in app._broker_desk_home_model.day_net_amount
            assert app._broker_desk_home_model.body_contains_action_authority() is False

            desk = app.query_one("#broker-desk", BrokerDesk)
            assert desk.display is True
            # Hero amount painted
            amt = str(desk.query_one("#bd-amt").content)
            assert "11.46" in amt
            hub = str(desk.query_one("#bd-hub").content)
            assert "m top" in hub or " m " in f" {hub} "

            # Hub keys still open deep pages (plain text)
            app.action_broker_matrix()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "matrix":
                    break
            assert "MATRIX_YP" in app._detail_text
            assert app.query_one("#broker-desk", BrokerDesk).display is False

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app.query_one("#broker-desk", BrokerDesk).display is True

    asyncio.run(scenario())
