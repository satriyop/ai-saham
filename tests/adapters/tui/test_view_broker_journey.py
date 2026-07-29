"""View broker journey: list → show → t/f/h → esc trail → v stock."""

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


def test_broker_hub_deep_and_esc_trail():
    async def scenario() -> None:
        desks = [
            SimpleNamespace(code="AK", type_label="Foreign"),
            SimpleNamespace(code="YP", type_label="Local"),
        ]
        pages: list[tuple[str, str]] = []

        def show_loader(code: str):
            pages.append(("show", code))
            return SimpleNamespace(text=f"SHOW_BODY_{code}", jump_ticker="BBRI")

        def top_loader(code: str) -> str:
            pages.append(("top", code))
            return f"TOP_BODY_{code}"

        def flow_loader(code: str) -> str:
            pages.append(("flow", code))
            return f"FLOW_BODY_{code}"

        def hist_loader(code: str) -> str:
            pages.append(("history", code))
            return f"HIST_BODY_{code}"

        viewed: list[str] = []

        def ticker_loader(ticker: str) -> str:
            viewed.append(ticker)
            return f"TICKER_DASH_{ticker}"

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: desks,
            broker_show_loader=show_loader,
            broker_top_loader=top_loader,
            broker_flow_loader=flow_loader,
            broker_history_loader=hist_loader,
            ticker_detail_loader=ticker_loader,
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
            assert app._stage == "broker-list"

            app._open_broker_desk_show()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app._broker_desk_code == "AK"
            assert "SHOW_BODY_AK" in app._detail_text
            assert "Actions (TUI)" in app._detail_text

            app.action_broker_top()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "top" and app._stage == "detail":
                    break
            assert "TOP_BODY_AK" in app._detail_text

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert "SHOW_BODY_AK" in app._detail_text

            app.action_broker_flow()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "flow":
                    break
            assert "FLOW_BODY_AK" in app._detail_text

            app.action_broker_history()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "history":
                    break
            assert "HIST_BODY_AK" in app._detail_text

            app.action_broker_jump_ticker()
            for _ in range(40):
                await pilot.pause(0.05)
                if viewed:
                    break
            assert viewed == ["BBRI"]
            assert "View · ticker show · BBRI" in app._board_title
            assert app._view_from_desk is True

            await pilot.press("escape")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._broker_page == "show":
                    break
            assert app._broker_page == "show"
            assert app._broker_desk_code == "AK"

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "broker-list"

            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

            # Desk keys must not fire on board
            app.action_broker_top()
            assert app._stage == "accum"

    asyncio.run(scenario())
