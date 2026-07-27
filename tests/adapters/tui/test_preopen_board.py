"""Phase 3 — pre-open presenter + injected board load."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.preopen_presenter import PreOpenPresenter
from src.adapters.tui.state import ScreenStatus


def _candidate(ticker: str = "BBRI") -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        iep=4820,
        iep_gap_pct=Decimal("1.8"),
        gap_pct=Decimal("1.8"),
        iev=12_400_000,
        iev_intensity=1.34,
        opening_broker_backing_tag="BACKED",
        trend_signal="BULLISH",
    )


def _payload(tickers: list[str]) -> SimpleNamespace:
    cands = [_candidate(t) for t in tickers]
    result = SimpleNamespace(candidates=cands)
    response = SimpleNamespace(result=result, warnings=[])
    return SimpleNamespace(response=response, snapshot_date="2026-07-25", warnings=())


def test_preopen_presenter_dense_fields():
    view = PreOpenPresenter().present(_payload(["BBRI", "BBCA"]))
    assert len(view.rows) == 2
    assert view.rows[0].ticker == "BBRI"
    assert view.rows[0].grade == "A"
    assert "+" in view.rows[0].delta_pct or view.rows[0].delta_pct.startswith("1")


def test_preopen_controller_empty_when_no_response():
    controller = BoardController(
        lambda: SimpleNamespace(response=None, snapshot_date=None, warnings=("none",)),
        empty_when=lambda p: getattr(p, "response", None) is None,
    )
    gen = controller.begin()
    states = []

    def dispatch(cb, *a):
        cb(*a)

    controller.execute_generation(gen, dispatch=dispatch, listener=states.append)
    assert states[-1].status is ScreenStatus.EMPTY


def test_cockpit_preopen_board_from_fake():
    async def scenario() -> None:
        payload = _payload(["BBRI", "BMRI"])
        loader = lambda: payload  # noqa: E731
        app = CockpitApp(
            preopen_loader=loader,
            preopen_controller=BoardController(
                loader,
                empty_when=lambda p: (
                    not getattr(
                        getattr(getattr(p, "response", None), "result", None),
                        "candidates",
                        True,
                    )
                ),
            ),
            preopen_presenter=PreOpenPresenter(),
        )
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app._run_command("screen-preopen")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "preopen" and len(app._rows) == 2:
                    break
            assert app._stage == "preopen"
            assert app._focus_ticker == "BBRI"
            assert app._evidence_text

    asyncio.run(scenario())
