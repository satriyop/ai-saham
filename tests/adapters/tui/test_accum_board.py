"""Phase 2 — accumulation board controller/presenter with injected fakes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.state import ScreenStatus


def _fake_candidate(ticker: str, score: float = 80.0) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        accum_score=score,
        rsi=50.0,
        volume_ratio=1.2,
        setup_phase=None,
        trade_setup=SimpleNamespace(action=SimpleNamespace(value="WATCH")),
        risk_assessment=None,
        name=f"{ticker} Corp",
    )


def _fake_result(tickers: list[str]) -> SimpleNamespace:
    candidates = [_fake_candidate(t) for t in tickers]
    projection = SimpleNamespace(
        candidates=candidates,
        window_days=7,
        data_as_of={"latest_candle_date": "2026-07-25"},
    )
    return SimpleNamespace(single_projection=projection, multi_projection=None, warnings=())


def test_accum_presenter_maps_rows():
    view = AccumPresenter().present(_fake_result(["BBRI", "BBCA"]))
    assert len(view.rows) == 2
    assert view.rows[0].ticker == "BBRI"
    assert view.rows[0].score == "80"
    assert "2 names" in view.meta


def test_board_controller_ready_and_stale_generation():
    calls: list[int] = []

    def loader():
        calls.append(1)
        return _fake_result(["BBRI"])

    controller = BoardController(loader)
    gen = controller.begin()
    delivered: list = []

    def dispatch(cb, *args):
        cb(*args)

    controller.execute_generation(
        gen,
        dispatch=dispatch,
        listener=lambda s: delivered.append(s),
    )
    assert delivered[-1].status is ScreenStatus.READY
    assert len(calls) == 1

    # stale generation ignored
    stale = gen
    controller.begin()
    controller.execute_generation(
        stale,
        dispatch=dispatch,
        listener=lambda s: delivered.append(("stale", s)),
    )
    assert not any(item[0] == "stale" for item in delivered if isinstance(item, tuple))


def test_cockpit_loads_accum_from_injected_loader():
    async def scenario() -> None:
        result = _fake_result(["BBRI", "BBCA", "BMRI"])
        controller = BoardController(lambda: result)
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_controller=controller,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app._run_command("screen-accum")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and len(app._rows) == 3:
                    break
            assert app._stage == "accum"
            assert len(app._rows) == 3
            assert app._focus_ticker == "BBRI"
            app._run_command("view-ticker")
            await pilot.pause()
            assert app._stage == "detail"
            assert "BBRI" in app._detail_text
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())
