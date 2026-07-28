"""Accumulation desk board (option B) — controller/presenter with fakes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.shared.score_display_labels import ACCUM, SIGNAL
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.state import ScreenStatus


def _fake_candidate(
    ticker: str,
    *,
    accum: float = 62.2,
    signal: int = 79,
    action: str = "WATCH",
    phase: str = "ACCUMULATION",
    streak: int = 6,
    rsi: float = 60.65,
    net_buy_ratio: float = 0.857,
    disc: float = -1.24,
    price: float = 1020,
    gate_triggered: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        accum_score=accum,
        rsi=rsi,
        consecutive_streak=streak,
        net_buy_ratio=net_buy_ratio,
        vwap_discount_pct=disc,
        current_price=price,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value=phase)),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(
                value=action,
                short=(
                    "BLOCKED(struct)"
                    if action == "BLOCKED_STRUCTURAL"
                    else "BLOCKED(exec)"
                    if action == "BLOCKED_EXECUTION"
                    else action
                ),
            ),
            rationale="test",
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=signal, strength=SimpleNamespace(value="STRONG"))
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=gate_triggered,
            gate_is_structural=False,
            rationale=("all gates passed",) if not gate_triggered else ("blocked",),
        ),
        name=f"{ticker} Corp",
    )


def _fake_result(tickers: list[str]) -> SimpleNamespace:
    # Signal-sorted like CLI default
    specs = [
        ("PGEO", 79, 62.2),
        ("INDF", 71, 56.7),
        ("BBTN", 70, 79.2),
    ]
    by_ticker = {t: (sig, acc) for t, sig, acc in specs}
    candidates = []
    for t in tickers:
        sig, acc = by_ticker.get(t, (50, 50.0))
        candidates.append(_fake_candidate(t, signal=sig, accum=acc))
    projection = SimpleNamespace(
        candidates=candidates,
        window_days=7,
        data_as_of={"latest_candle_date": "2026-07-25"},
        applied_filters=SimpleNamespace(sort_by="signal", top=40),
    )
    return SimpleNamespace(single_projection=projection, multi_projection=None, warnings=())


def test_accum_presenter_option_b_columns():
    view = AccumPresenter().present(_fake_result(["PGEO", "INDF", "BBTN"]))
    assert view.columns[1] == SIGNAL
    assert view.columns[2] == ACCUM
    assert "Signal" in view.columns or SIGNAL in view.columns
    assert len(view.rows) == 3

    row = view.rows[0]
    assert row.ticker == "PGEO"
    assert row.signal == "79"  # SignalEngine, not Accum
    assert row.accum == "62.2"  # Accum composite
    assert row.streak == "6"
    assert row.rsi == "60.7" or row.rsi == "60.6" or row.rsi.startswith("60")
    assert row.net_pct == "86%"
    assert row.disc_pct.startswith("-1.2")
    assert row.price == "1,020"
    assert row.gate == "OPEN"
    assert row.phase == "ACCUM"  # short phase label
    assert "sort signal" in view.meta
    assert "window 7d" in view.meta


def test_accum_presenter_gate_blocked():
    c = _fake_candidate("SCMA", gate_triggered="BandarGate", action="BLOCKED_STRUCTURAL")
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[c],
                window_days=7,
                data_as_of={},
                applied_filters=SimpleNamespace(sort_by="signal", top=10),
            )
        )
    )
    assert view.rows[0].gate == "BLOCKED"


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
        result = _fake_result(["PGEO", "INDF", "BBTN"])
        controller = BoardController(lambda: result)
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_controller=controller,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            app._run_command("screen-accum")
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and len(app._rows) == 3:
                    break
            assert app._stage == "accum"
            assert len(app._rows) == 3
            assert app._focus_ticker == "PGEO"
            assert app._rows[0].signal == "79"
            assert app._rows[0].accum == "62.2"
            app._open_detail()  # board Enter inspect (not palette view-ticker)
            await pilot.pause()
            assert app._stage == "detail"
            assert "PGEO" in app._detail_text
            assert "Signal" in app._detail_text or "79" in app._detail_text
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())
