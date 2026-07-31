"""Broker calendar month-grid paint hierarchy (mock desk-cal parity)."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_calendar_model import (
    DOW_LABELS,
    MAX_GRID_CELLS,
    build_broker_desk_calendar_model,
    build_month_grid_cells,
    format_broker_desk_calendar_scraper_text,
    format_calendar_cell_markup,
)
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.widgets.broker_calendar_desk import BrokerCalendarDesk
from src.domain.entities.broker_flow import BrokerType


def _day(
    d: date,
    *,
    top: str,
    net: str,
    buy: str | None = None,
    sell: str | None = None,
) -> SimpleNamespace:
    nv = Decimal(net)
    bv = Decimal(buy) if buy is not None else (nv if nv > 0 else Decimal("0"))
    sv = Decimal(sell) if sell is not None else (-nv if nv < 0 else Decimal("0"))
    return SimpleNamespace(
        date=d,
        net_value=nv,
        buy_value=bv,
        sell_value=sv,
        top_ticker=top,
        top_net=nv,
        ticker_count=2,
    )


def _result(*days: SimpleNamespace, as_of: date = date(2026, 7, 29)) -> SimpleNamespace:
    return SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        as_of=as_of,
        sessions_cached=len(days),
        scope_note="Tracked desk activity only · not market foreign total",
        days=days,
    )


def test_month_grid_mon_start_pad_for_july_2026():
    """Jul 2026 starts Wednesday → pad 2 (Mon, Tue)."""
    sessions = [
        _day(date(2026, 7, 1), top="BBRI", net="2100000000"),
        _day(
            date(2026, 7, 29),
            top="AMMN",
            net="11500000000",
            buy="14200000000",
            sell="2700000000",
        ),
    ]
    cells, month_label, summary, n = build_month_grid_cells(sessions, as_of=date(2026, 7, 29))
    assert month_label == "Jul 2026"
    assert n == 2
    assert cells[0].kind == "pad"
    assert cells[1].kind == "pad"
    # day 1 at index 2
    assert cells[2].kind == "session"
    assert cells[2].day_num == 1
    assert cells[2].top_ticker == "BBRI"
    # day 29 at index 2 + 28 = 30
    c29 = cells[2 + 28]
    assert c29.kind == "session"
    assert c29.day_num == 29
    assert c29.top_ticker == "AMMN"
    assert c29.is_as_of is True
    assert c29.tone == "pos"
    assert "AMMN" in format_calendar_cell_markup(c29)
    assert "sessions" in summary.lower()
    assert "desk only" in summary.lower()
    assert len(cells) == MAX_GRID_CELLS


def test_calendar_model_exposes_grid_hierarchy_not_just_rows():
    model = build_broker_desk_calendar_model(
        _result(
            _day(date(2026, 7, 14), top="AMMN", net="4000000000"),
            _day(date(2026, 7, 29), top="BUMI", net="-4400000000"),
        )
    )
    assert model.empty is False
    assert model.month_label == "Jul 2026"
    assert model.legend
    assert "top stock" in model.legend.lower()
    assert len(model.cells) == MAX_GRID_CELLS
    sessions = [c for c in model.cells if c.kind == "session"]
    assert len(sessions) == 2
    tickers = {c.top_ticker for c in sessions}
    assert "AMMN" in tickers and "BUMI" in tickers
    assert model.body_contains_action_authority() is False
    # scraper still has row list for loaders
    text = format_broker_desk_calendar_scraper_text(model)
    assert "Month · Jul 2026" in text
    assert "AMMN" in text


def test_calendar_widget_paints_month_grid_hierarchy():
    async def scenario() -> None:
        model = build_broker_desk_calendar_model(
            _result(
                _day(date(2026, 7, 1), top="BBRI", net="1000000000"),
                _day(date(2026, 7, 29), top="AMMN", net="11500000000"),
            )
        )
        app = CockpitApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#broker-calendar-desk", BrokerCalendarDesk)
            desk.display = True
            desk.paint(model)

            title = str(desk.query_one("#ca-title").content)
            assert "Calendar · YP · Jul 2026" in title
            assert "Jul" in title

            summary = str(desk.query_one("#ca-summary").content)
            assert "sessions" in summary.lower()
            assert "desk only" in summary.lower() or "not market foreign" in summary.lower()

            # DOW headers Mon–Sun
            for i, lab in enumerate(DOW_LABELS):
                assert lab in str(desk.query_one(f"#ca-dow-{i}").content)

            # Not a row-dump primary: no ca-row-0 head columns dump
            assert not desk.query("#ca-row-0")
            assert not desk.query("#ca-head")

            # Day 29 cell carries ticker + net hierarchy
            # Jul 2026: pad 2 + day 29 → index 30
            cell29 = str(desk.query_one("#ca-cell-30").content)
            assert "AMMN" in cell29
            assert "29" in cell29

            cell1 = str(desk.query_one("#ca-cell-2").content)
            assert "BBRI" in cell1

            legend = str(desk.query_one("#ca-legend").content)
            assert "top stock" in legend.lower() or "net" in legend.lower()

            hub = str(desk.query_one("#ca-hub").content)
            assert "c calendar" in hub.lower() or "m top" in hub.lower()
            assert "ENTER" not in hub.upper().replace("CENTER", "")

            # Session cell has session class
            classes = desk.query_one("#ca-cell-30").classes
            assert "session" in classes
            assert "asof" in classes

    asyncio.run(scenario())


def test_cockpit_hub_c_paints_grid_not_row_dump():
    async def scenario() -> None:
        cal_model = build_broker_desk_calendar_model(
            _result(_day(date(2026, 7, 29), top="AMMN", net="1000000000"))
        )

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

        def _accum():
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

        app = CockpitApp(
            accum_loader=_accum,
            accum_controller=BoardController(_accum),
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
        async with app.run_test(size=(140, 50)) as pilot:
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
            desk = app.query_one("#broker-calendar-desk", BrokerCalendarDesk)
            assert desk.display is True
            title = str(desk.query_one("#ca-title").content)
            assert "Jul 2026" in title
            cell29 = str(desk.query_one("#ca-cell-30").content)
            assert "AMMN" in cell29
            # Primary paint is grid cells, not Date/Top/Net header dump
            assert not desk.query("#ca-row-0")

    asyncio.run(scenario())
