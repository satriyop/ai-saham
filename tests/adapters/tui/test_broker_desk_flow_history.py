"""Broker flow + history models/widgets — Stage 4."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_flow_model import (
    build_broker_desk_flow_model,
    format_broker_desk_flow_scraper_text,
)
from src.adapters.tui.broker_desk_history_model import (
    build_broker_desk_history_model,
    format_broker_desk_history_scraper_text,
)
from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.broker_flow_desk import BrokerFlowDesk
from src.adapters.tui.widgets.broker_history_desk import BrokerHistoryDesk
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


def test_build_flow_model_newest_first_and_bars():
    result = SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        scope_note="Tracked desk",
        days=(
            SimpleNamespace(
                date=date(2026, 7, 28),
                net_value=Decimal("1000000000"),
                net_lot=10,
                ticker_count=2,
            ),
            SimpleNamespace(
                date=date(2026, 7, 29),
                net_value=Decimal("2000000000"),
                net_lot=20,
                ticker_count=3,
            ),
        ),
    )
    model = build_broker_desk_flow_model(result)
    assert model.empty is False
    assert model.days[0].date_label == "2026-07-29"  # newest first
    assert model.days[0].bar_pct == 100
    assert model.days[1].bar_pct == 50
    assert model.days[0].net_display.startswith("+")
    assert "not market foreign" in model.scope_note
    assert model.body_contains_action_authority() is False
    assert "Flow" in format_broker_desk_flow_scraper_text(model)


def test_build_history_model_rows():
    result = SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.LOCAL,
        scope_note="Tracked desk",
        pinned_ticker=None,
        flows=(
            SimpleNamespace(
                date=date(2026, 7, 29),
                ticker="AMMN",
                net_value=Decimal("5000000000"),
                net_lot=100,
            ),
            SimpleNamespace(
                date=date(2026, 7, 28),
                ticker="BBCA",
                net_value=Decimal("-1000000000"),
                net_lot=-20,
            ),
        ),
    )
    model = build_broker_desk_history_model(result)
    assert model.rows[0].ticker == "AMMN"
    assert model.rows[0].tone == "pos"
    assert model.rows[1].ticker == "BBCA"
    assert model.jump_ticker == "AMMN"
    assert model.body_contains_action_authority() is False
    assert "History" in format_broker_desk_history_scraper_text(model)


def test_cockpit_paints_flow_and_history_on_f_h():
    async def scenario() -> None:
        flow_model = build_broker_desk_flow_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP Desk",
                broker_type=BrokerType.FOREIGN,
                scope_note="Tracked",
                days=(
                    SimpleNamespace(
                        date=date(2026, 7, 29),
                        net_value=Decimal("3000000000"),
                        net_lot=50,
                        ticker_count=4,
                    ),
                ),
            )
        )
        hist_model = build_broker_desk_history_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP Desk",
                broker_type=BrokerType.FOREIGN,
                scope_note="Tracked",
                pinned_ticker=None,
                flows=(
                    SimpleNamespace(
                        date=date(2026, 7, 29),
                        ticker="AMMN",
                        net_value=Decimal("1000000000"),
                        net_lot=10,
                    ),
                ),
            )
        )

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

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: [SimpleNamespace(code="YP", type_label="Foreign")],
            broker_show_loader=show_loader,
            broker_top_loader=lambda c: f"TOP_{c}",
            broker_flow_loader=lambda c: SimpleNamespace(
                text=f"FLOW_BODY_{c}", model=flow_model, jump_ticker=None
            ),
            broker_history_loader=lambda c: SimpleNamespace(
                text=f"HIST_BODY_{c}", model=hist_model, jump_ticker="AMMN"
            ),
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
                if app._broker_page == "show":
                    break

            app.action_broker_flow()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "flow":
                    break
            assert app._broker_page == "flow"
            assert app._broker_desk_flow_model is not None
            assert "FLOW_BODY_YP" in app._detail_text
            fl = app.query_one("#broker-flow-desk", BrokerFlowDesk)
            assert fl.display is True
            assert "2026-07-29" in str(fl.query_one("#fl-date-0").content)
            assert app.query_one("#broker-desk", BrokerDesk).display is False

            app.action_broker_history()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "history":
                    break
            assert app._broker_page == "history"
            assert app._broker_desk_history_model is not None
            assert "HIST_BODY_YP" in app._detail_text
            hi = app.query_one("#broker-history-desk", BrokerHistoryDesk)
            assert hi.display is True
            assert "AMMN" in str(hi.query_one("#hi-t-0").content)
            assert fl.display is False

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app.query_one("#broker-desk", BrokerDesk).display is True

    asyncio.run(scenario())
