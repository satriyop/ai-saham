"""Remaining cockpit redesign slices: calendar · judge d · prompt rail."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_calendar_model import (
    build_broker_desk_calendar_model,
    format_broker_desk_calendar_scraper_text,
)
from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_calendar_desk import BrokerCalendarDesk
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.judge_desk import JudgeDesk
from src.domain.entities.broker_flow import BrokerType


def _accum_payload():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=50.0,
        signal_assessment=SimpleNamespace(
            score=84,
            band="MODERATE",
            net_buy_ratio=0.5,
            consecutive_streak=2,
        ),
        trade_setup=SimpleNamespace(action="WATCH", rationale="ok"),
        risk_assessment=SimpleNamespace(status="OPEN", blocking_gates=()),
        setup_phase=SimpleNamespace(phase="COMPRESS"),
        consecutive_streak=2,
        rsi=48.2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.2,
        current_price=6275,
        name="BBCA",
        source=object(),
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


def test_calendar_model_desk_scope_not_market_foreign():
    result = SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        as_of=date(2026, 7, 29),
        sessions_cached=5,
        scope_note="Tracked desk activity only · not market foreign total",
        days=(
            SimpleNamespace(
                date=date(2026, 7, 29),
                net_value=Decimal("5000000000"),
                buy_value=Decimal("8000000000"),
                sell_value=Decimal("3000000000"),
                top_ticker="AMMN",
                top_net=Decimal("4000000000"),
                ticker_count=3,
            ),
        ),
    )
    model = build_broker_desk_calendar_model(result)
    assert model.empty is False
    assert model.days[0].top_ticker == "AMMN"
    assert "not market foreign" in model.scope_note.lower()
    assert model.body_contains_action_authority() is False
    text = format_broker_desk_calendar_scraper_text(model)
    assert "AMMN" in text
    assert "foreign total" in text.lower() or "not market foreign" in text.lower()


def test_calendar_empty_path():
    model = build_broker_desk_calendar_model(None, code="AK")
    assert model.empty is True
    assert "fetch" in model.empty_reason.lower() or "no broker" in model.empty_reason.lower()


def test_cockpit_calendar_hub_c_and_esc():
    async def scenario() -> None:
        cal_model = build_broker_desk_calendar_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP Desk",
                broker_type=BrokerType.FOREIGN,
                as_of=date(2026, 7, 29),
                sessions_cached=1,
                scope_note="Tracked desk · not market foreign total",
                days=(
                    SimpleNamespace(
                        date=date(2026, 7, 29),
                        net_value=Decimal("1000000000"),
                        buy_value=Decimal("2000000000"),
                        sell_value=Decimal("1000000000"),
                        top_ticker="AMMN",
                        top_net=Decimal("1000000000"),
                        ticker_count=1,
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
            broker_calendar_loader=lambda c: SimpleNamespace(
                text=f"CAL_BODY_{c}", model=cal_model, jump_ticker="AMMN"
            ),
            broker_top_loader=lambda c: f"TOP_{c}",
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
                if app._broker_page == "show":
                    break
            app.action_broker_calendar()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "cal":
                    break
            assert app._broker_page == "cal"
            assert app._broker_desk_calendar_model is not None
            assert "CAL_BODY_YP" in app._detail_text
            desk = app.query_one("#broker-calendar-desk", BrokerCalendarDesk)
            assert desk.display is True
            # Month grid: day 29 (Jul 2026 Mon-start) lives at cell index 30
            assert "AMMN" in str(desk.query_one("#ca-cell-30").content)
            assert "Jul" in str(desk.query_one("#ca-title").content)
            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app.query_one("#broker-desk", BrokerDesk).display is True

    asyncio.run(scenario())


def test_judge_detail_toggle_and_ticker_d_dispatch():
    """Real path: _open_detail → compact → action_toggle_detail repaints full."""

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=lambda t: f"TICKER_BODY_{t}",
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._row_index = 0
            app._focus_ticker = app._rows[0].ticker
            app._open_detail()
            await pilot.pause(0.15)
            assert app._status_note == "judge"
            judge = app.query_one("#judge-desk", JudgeDesk)
            assert judge.display is True
            # Compact: phase timeline primary; decision stack + detail chips via d
            assert app._judge_detail_open is False
            assert app.query_one("#jd-phase").display is True
            assert app.query_one("#jd-decision").display is False
            assert "detail · d" in str(app.query_one("#jd-flag-detail").content)
            assert "is-on" not in app.query_one("#jd-flag-detail").classes
            app.action_toggle_detail()
            await pilot.pause(0.15)
            assert app._judge_detail_open is True
            # Must repaint through _refresh_chrome — no manual paint call
            assert app.query_one("#jd-decision").display is True
            assert "is-on" in app.query_one("#jd-flag-detail").classes
            foot = str(app.query_one("#jd-footer").content).lower()
            assert "d " in foot or "collapse" in foot or "detail" in foot
            # Switch to view-ticker: d toggles ticker only
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._status_note == "view ticker":
                    break
            assert app._status_note == "view ticker"
            app._ticker_detail_open = False
            judge_flag_before = app._judge_detail_open
            app.action_toggle_detail()
            await pilot.pause(0.05)
            assert app._ticker_detail_open is True
            assert app._judge_detail_open is judge_flag_before

    asyncio.run(scenario())


def test_prompt_rail_composed_idle_non_action():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.05)
            from textual.widgets import Input

            rail = app.query_one("#prompt-rail")
            assert rail is not None
            aff = str(app.query_one("#prompt-affordance").content)
            assert "›" in aff or aff.strip() != ""
            inp = app.query_one("#prompt-input", Input)
            ph = str(getattr(inp, "placeholder", "") or "").lower()
            assert "idle" in ph or "not action" in ph
            assert "not action" in ph or "prompt" in ph
            mode = str(app.query_one("#prompt-mode").content).lower()
            assert "idle" in mode

    asyncio.run(scenario())
