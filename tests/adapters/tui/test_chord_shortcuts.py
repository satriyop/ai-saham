"""Two-key chords: s a / s p / v t / v b (wired, not palette labels only)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.commands import COCKPIT_COMMANDS
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


def test_palette_labels_match_chords():
    by_id = {c.command_id: c for c in COCKPIT_COMMANDS}
    assert by_id["screen-accum"].shortcut == "s a"
    assert by_id["screen-preopen"].shortcut == "s p"
    assert by_id["view-ticker"].shortcut == "v t"
    assert by_id["view-broker"].shortcut == "v b"


def test_chord_v_t_opens_view_ticker_v_b_opens_broker():
    async def scenario() -> None:
        viewed: list[str] = []
        broker_loads = 0

        def ticker_loader(t: str) -> str:
            viewed.append(t)
            return f"DASH_{t}"

        def broker_list():
            nonlocal broker_loads
            broker_loads += 1
            return [SimpleNamespace(code="AK", type_label="Foreign")]

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            ticker_detail_loader=ticker_loader,
            broker_list_loader=broker_list,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._focus_ticker == "BBCA"

            await pilot.press("v")
            assert app._chord_prefix == "v"
            await pilot.press("t")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "detail" and app._status_note == "view ticker":
                    break
            assert viewed == ["BBCA"]
            assert app._chord_prefix is None

            await pilot.press("v")
            await pilot.press("b")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break
            assert broker_loads == 1
            assert app._stage == "broker-list"

    asyncio.run(scenario())


def test_chord_s_a_reloads_accum_s_p_loads_preopen():
    async def scenario() -> None:
        accum_n = 0
        preopen_n = 0

        def accum():
            nonlocal accum_n
            accum_n += 1
            return _accum_payload()

        def preopen():
            nonlocal preopen_n
            preopen_n += 1
            return SimpleNamespace(
                snapshot_date="2026-03-01",
                warnings=(),
                candidates=[
                    SimpleNamespace(
                        ticker="BBRI",
                        iep="100",
                        delta_pct="1",
                        iev="1",
                        ncp="1",
                        delta_iev="0",
                        grade="A",
                        risk="LOW",
                        name="BBRI",
                    )
                ],
            )

        from src.adapters.tui.presenters.preopen_presenter import PreOpenPresenter

        app = CockpitApp(
            accum_loader=accum,
            accum_controller=BoardController(accum),
            accum_presenter=AccumPresenter(),
            preopen_loader=preopen,
            preopen_controller=BoardController(preopen),
            preopen_presenter=PreOpenPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum":
                    break
            base_accum = accum_n

            await pilot.press("s")
            await pilot.press("p")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "preopen":
                    break
            assert preopen_n >= 1
            assert app._stage == "preopen"

            await pilot.press("s")
            await pilot.press("a")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum":
                    break
            assert accum_n > base_accum
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_v_on_desk_hub_still_jumps_not_chord():
    async def scenario() -> None:
        viewed: list[str] = []

        def show_loader(code: str):
            return SimpleNamespace(text=f"SHOW_{code}", jump_ticker="BBRI")

        def ticker_loader(t: str) -> str:
            viewed.append(t)
            return f"D_{t}"

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            broker_list_loader=lambda: [SimpleNamespace(code="AK", type_label="F")],
            broker_show_loader=show_loader,
            ticker_detail_loader=ticker_loader,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum":
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
            assert app._desk_hub_active()

            await pilot.press("v")
            # Immediate jump — no chord arm
            assert app._chord_prefix is None
            for _ in range(40):
                await pilot.pause(0.05)
                if viewed:
                    break
            assert viewed == ["BBRI"]

    asyncio.run(scenario())


def test_escape_cancels_chord_without_leaving_board():
    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum":
                    break
            await pilot.press("v")
            assert app._chord_prefix == "v"
            await pilot.press("escape")
            await pilot.pause()
            assert app._chord_prefix is None
            assert app._stage == "accum"

    asyncio.run(scenario())
