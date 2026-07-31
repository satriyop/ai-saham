"""Remaining visual-parity frames: pre-open inspect, flags, f/h, ticker chips.

Design: docs/design/tui-cockpit-opencode.md. Headless paint on shipped path.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.broker_desk_flow_model import build_broker_desk_flow_model
from src.adapters.tui.broker_desk_history_model import build_broker_desk_history_model
from src.adapters.tui.broker_desk_home_model import build_broker_desk_home_model
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.empty_stage_body import format_empty_stage_body
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.paper_log_display import format_paper_confirm_body
from src.adapters.tui.preopen_inspect_model import build_preopen_inspect_model
from src.adapters.tui.presenters.preopen_presenter import PreOpenPresenter
from src.adapters.tui.ticker_desk_model import build_ticker_desk_model_from_dashboard
from src.adapters.tui.widgets.broker_desk import BrokerDesk
from src.adapters.tui.widgets.broker_flow_desk import BrokerFlowDesk
from src.adapters.tui.widgets.broker_history_desk import BrokerHistoryDesk
from src.adapters.tui.widgets.preopen_inspect_desk import PreopenInspectDesk
from src.adapters.tui.widgets.ticker_desk import TickerDesk
from src.domain.entities.broker_flow import BrokerType


def test_preopen_inspect_model_flags_not_action():
    row = SimpleNamespace(
        ticker="BBRI",
        iep="4,820",
        delta_pct="+1.8",
        iev="12.4M",
        ncp="1.34",
        delta_iev="1.34",
        grade="A",
        risk="clear",
        evidence="ok",
        source=SimpleNamespace(
            trend_signal="BULLISH",
            opening_broker_backing_tag="BACKED",
            opening_broker_backing_score=0.9,
            opening_broker_buy_streak=3,
        ),
    )
    model = build_preopen_inspect_model(
        row,
        rank=1,
        total=3,
        snapshot_date="2026-07-25",
        warnings=("note: snapshot path",),
    )
    assert model.ticker == "BBRI"
    assert model.grade == "A"
    assert model.has_auction is True
    assert model.has_warn is True
    keys = {f.key for f in model.flags}
    assert keys == {"detail", "why", "auction_plus", "warn"}
    assert model.body_contains_action_authority() is False


def test_preopen_inspect_desk_hierarchy_paint():
    async def scenario() -> None:
        row = SimpleNamespace(
            ticker="BBRI",
            iep="4,820",
            delta_pct="+1.8",
            iev="12.4M",
            ncp="1.34",
            delta_iev="1.34",
            grade="A",
            risk="clear",
            evidence="ok",
            source=SimpleNamespace(
                trend_signal="BULLISH",
                opening_broker_backing_tag="BACKED",
                opening_broker_backing_score=0.9,
                opening_broker_buy_streak=3,
            ),
        )
        model = build_preopen_inspect_model(row, warnings=("w1",))
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#preopen-inspect-desk", PreopenInspectDesk)
            desk.display = True
            desk.paint(model, detail_open=False)
            assert "BBRI" in str(desk.query_one("#poi-title").content)
            assert "A" in str(desk.query_one("#poi-grade").content)
            assert "4,820" in str(desk.query_one("#poi-levels-body").content)
            assert "why" in str(desk.query_one("#poi-flag-why").content)
            assert "auction+" in str(desk.query_one("#poi-flag-auction_plus").content)
            assert desk.query_one("#poi-panel-why").display is False
            desk.paint(model, detail_open=True)
            assert desk.query_one("#poi-panel-why").display is True
            assert "is-on" in desk.query_one("#poi-flag-why").classes
            assert "BULLISH" in str(desk.query_one("#poi-auction-body").content)

    asyncio.run(scenario())


def test_cockpit_enter_paints_preopen_inspect_widget():
    async def scenario() -> None:
        cand = SimpleNamespace(
            ticker="BBRI",
            iep=4820,
            iep_gap_pct=Decimal("1.8"),
            gap_pct=Decimal("1.8"),
            iev=12_400_000,
            iev_intensity=1.34,
            opening_broker_backing_tag="BACKED",
            trend_signal="BULLISH",
            opening_broker_backing_score=0.9,
            opening_broker_buy_streak=3,
        )
        payload = SimpleNamespace(
            response=SimpleNamespace(result=SimpleNamespace(candidates=[cand]), warnings=[]),
            snapshot_date="2026-07-25",
            warnings=("note",),
        )
        app = CockpitApp(
            preopen_loader=lambda: payload,
            preopen_controller=BoardController(lambda: payload),
            preopen_presenter=PreOpenPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app._run_command("screen-preopen")
            for _ in range(50):
                await pilot.pause(0.05)
                if app._stage == "preopen" and app._rows:
                    break
            assert app._stage == "preopen"
            app._row_index = 0
            app._focus_ticker = app._rows[0].ticker
            app._open_detail()
            await pilot.pause(0.15)
            assert app._status_note == "inspect"
            desk = app.query_one("#preopen-inspect-desk", PreopenInspectDesk)
            assert desk.display is True
            assert "BBRI" in str(desk.query_one("#poi-title").content)
            assert "why" in str(desk.query_one("#poi-flag-why").content)
            assert app.query_one("#stage-body").display is False

    asyncio.run(scenario())


def test_broker_home_deep_flag_chips():
    async def scenario() -> None:
        home = build_broker_desk_home_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP Desk",
                broker_type=BrokerType.FOREIGN,
                as_of=date(2026, 7, 29),
                day_net_value=Decimal("1e9"),
                day_net_lot=10,
                day_ticker_count=1,
                top_buy_stocks=(SimpleNamespace(ticker="AMMN", net_value=Decimal("1e9")),),
                top_sell_stocks=(),
                scope_note="Tracked desk",
            )
        )
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            desk = app.query_one("#broker-desk", BrokerDesk)
            desk.display = True
            desk.paint(home)
            assert "deep.t" in str(desk.query_one("#bd-flag-t").content)
            assert "deep.m" in str(desk.query_one("#bd-flag-m").content)

    asyncio.run(scenario())


def test_flow_history_structured_density_not_row_dump_only():
    async def scenario() -> None:
        flow = build_broker_desk_flow_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP",
                broker_type=BrokerType.FOREIGN,
                scope_note="Tracked desk · not market foreign",
                days=(
                    SimpleNamespace(
                        date=date(2026, 7, 29),
                        net_value=Decimal("1e9"),
                        net_lot=10,
                        ticker_count=2,
                    ),
                ),
            )
        )
        hist = build_broker_desk_history_model(
            SimpleNamespace(
                broker_code="YP",
                broker_name="YP",
                broker_type=BrokerType.FOREIGN,
                scope_note="Tracked",
                pinned_ticker=None,
                flows=(
                    SimpleNamespace(
                        date=date(2026, 7, 29),
                        ticker="AMMN",
                        net_value=Decimal("1e9"),
                        net_lot=5,
                    ),
                ),
            )
        )
        app = CockpitApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            fl = app.query_one("#broker-flow-desk", BrokerFlowDesk)
            fl.display = True
            fl.paint(flow)
            assert "2026-07-29" in str(fl.query_one("#fl-date-0").content)
            assert "█" in str(fl.query_one("#fl-bar-0").content) or "░" in str(
                fl.query_one("#fl-bar-0").content
            )
            assert fl.query_one("#fl-panel")

            hi = app.query_one("#broker-history-desk", BrokerHistoryDesk)
            hi.display = True
            hi.paint(hist)
            assert "AMMN" in str(hi.query_one("#hi-t-0").content)
            assert hi.query_one("#hi-panel")

    asyncio.run(scenario())


def test_ticker_detail_flag_row_paint():
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
            assert "detail · d" in str(desk.query_one("#td-flag-detail").content)
            assert "is-on" not in desk.query_one("#td-flag-detail").classes
            # Design: single master chip only
            assert not desk.query("#td-flag-analyst")
            desk.paint(model, detail_open=True)
            assert "is-on" in desk.query_one("#td-flag-detail").classes

    asyncio.run(scenario())


def test_ticker_view_meta_header_no_not_action_chrome():
    """Live #view-meta for ticker is bible local cache / full · local cache only."""

    async def scenario() -> None:
        def loader(t: str):
            return build_ticker_desk_model_from_dashboard(
                SimpleNamespace(
                    ticker=t,
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
                    analyst=None,
                    ownership=None,
                    insider_txns=(),
                    iev_rows=(),
                    seasonality=None,
                    freshness=(),
                )
            )

        app = CockpitApp(ticker_detail_loader=loader)
        async with app.run_test(size=(140, 48)) as pilot:
            await pilot.pause(0.05)
            app._focus_ticker = "BBCA"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBCA",
                    signal="84",
                    accum="48",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._status_note == "view ticker":
                    break
            assert app._status_note == "view ticker"
            meta = str(app.query_one("#view-meta").content)
            assert "not Action" not in meta
            assert "local cache" in meta.lower()
            # d expand → full · local cache
            app.action_toggle_detail()
            await pilot.pause(0.1)
            meta2 = str(app.query_one("#view-meta").content)
            assert "not Action" not in meta2
            assert "full" in meta2.lower() and "local cache" in meta2.lower()
            # d collapse
            app.action_toggle_detail()
            await pilot.pause(0.1)
            meta3 = str(app.query_one("#view-meta").content)
            assert "not Action" not in meta3
            assert "local cache" in meta3.lower()

    asyncio.run(scenario())


def test_paper_and_health_opencode_density_copy():
    paper = format_paper_confirm_body(
        ticker="BBCA", entry="6225", stop="5900", target="6800", lots="3"
    )
    assert "PAPER TAPE" in paper
    assert "GEOMETRY" in paper
    assert "NOTEBOOK · PAPER ONLY" not in paper  # product tape language
    empty = format_empty_stage_body(cache_status="empty")
    assert "SESSION HEALTH" in empty or "No local market data" in empty
    assert "empty" in empty.lower()


def test_broker_list_flag_row_on_stage():
    async def scenario() -> None:
        app = CockpitApp(
            broker_list_loader=lambda: [
                SimpleNamespace(
                    code="YP",
                    type_label="Foreign",
                    has_partial_netx=True,
                )
            ],
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._stage = "broker-list"
            app._broker_rows = [
                SimpleNamespace(code="YP", type_label="Foreign", has_partial_netx=True)
            ]
            app._paint_board_flag_row()
            flags = app.query_one("#board-flag-row")
            assert flags.display is True
            from src.adapters.tui.widgets.flag_chip import FlagChip

            partial = app.query_one("#board-flag-partial_net", FlagChip)
            from_t = app.query_one("#board-flag-from_ticker", FlagChip)
            assert partial.flag_key == "partial_net"
            assert from_t.flag_key == "from_ticker"
            assert "is-on" in partial.classes

    asyncio.run(scenario())
