"""View ticker → b top desks → Enter desk show → esc trail."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


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


def test_stock_to_desks_enter_show_esc_trail():
    async def scenario() -> None:
        desks_payload = SimpleNamespace(
            ticker="BBCA",
            as_of="2026-03-01",
            note="summary tops · Net5 on stock sessions (1/2 desks)",
            rows=(
                SimpleNamespace(
                    code="AK",
                    type_label="Foreign",
                    role="buy",
                    day_net="30.00M",
                    net3="60.00M",
                    net5="210.00M",
                    net7="250.00M",
                    net10="250.00M",
                    net20="250.00M",
                    streak="3",
                    delta1="+10.00M",
                    as_of="2026-03-05",
                    has_pulse=True,
                ),
                SimpleNamespace(
                    code="YP",
                    type_label="Local",
                    role="sell",
                    day_net="-500.00M",
                    net3="—",
                    net5="—",
                    net7="—",
                    net10="—",
                    net20="—",
                    streak="—",
                    delta1="—",
                    as_of="2026-03-01",
                    has_pulse=False,
                ),
            ),
        )
        show_codes: list[str] = []
        desk_loads: list[str] = []
        viewed: list[str] = []

        def ticker_loader(ticker: str) -> str:
            viewed.append(ticker)
            return f"TICKER_DASH_{ticker}"

        def desks_loader(ticker: str):
            desk_loads.append(ticker)
            return desks_payload

        def show_loader(code: str):
            show_codes.append(code)
            return SimpleNamespace(text=f"SHOW_BODY_{code}", jump_ticker="BBRI")

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=ticker_loader,
            ticker_desks_loader=desks_loader,
            broker_show_loader=show_loader,
            broker_top_loader=lambda code: f"TOP_{code}",
            broker_flow_loader=lambda code: f"FLOW_{code}",
            broker_history_loader=lambda code: f"HIST_{code}",
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            assert app._focus_ticker == "BBCA"

            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._status_note == "view ticker":
                    break
            assert app._stage == "detail"
            assert "TICKER_DASH_BBCA" in app._detail_text
            assert "b top desks" in app._detail_text
            assert app._detail_return_stage == "accum"

            # b is no-op on inspect; only on view ticker
            app._status_note = "inspect"
            app.action_ticker_desks()
            assert app._stage == "detail"
            assert desk_loads == []
            app._status_note = "view ticker"

            app.action_ticker_desks()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "ticker-desks":
                    break
            assert app._stage == "ticker-desks"
            assert desk_loads == ["BBCA"]
            assert app._ticker_desks_stock == "BBCA"
            assert len(app._broker_rows) == 2
            assert app._focus_ticker == "AK"
            assert "as of 2026-03-01" in app._meta

            app._open_broker_desk_show(entry="ticker-desks")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app._broker_desk_code == "AK"
            assert app._desk_entry == "ticker-desks"
            assert "SHOW_BODY_AK" in app._detail_text
            assert "esc desks" in app._detail_text
            assert show_codes == ["AK"]

            app.action_broker_top()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "top":
                    break
            assert "TOP_AK" in app._detail_text

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app._desk_entry == "ticker-desks"

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "ticker-desks"
            assert app._ticker_desks_stock == "BBCA"
            # restore does not re-fetch
            assert desk_loads == ["BBCA"]

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._status_note == "view ticker":
                    break
            assert app._stage == "detail"
            assert app._status_note == "view ticker"
            assert app._focus_ticker == "BBCA"
            assert app._detail_return_stage == "accum"
            assert len(viewed) >= 2  # initial + esc from desks

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

            # b no-op on board
            app.action_ticker_desks()
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_ticker_desks_empty_payload_still_table():
    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=lambda t: f"D_{t}",
            ticker_desks_loader=lambda t: SimpleNamespace(
                ticker=t, as_of=None, note="no broker summary", rows=()
            ),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum":
                    break
            app._run_command("view-ticker")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._status_note == "view ticker":
                    break
            app.action_ticker_desks()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "ticker-desks":
                    break
            assert app._stage == "ticker-desks"
            assert app._broker_rows == []
            assert "0 desks" in app._meta

    asyncio.run(scenario())
