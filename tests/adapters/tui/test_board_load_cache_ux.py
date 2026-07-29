"""Cockpit keep-prior refresh + last-run snapshot open (criteria 1–4)."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

from src.adapters.tui.board_snapshot import (
    identity_from_live_payload,
    snapshot_from_board_view,
    write_accum_board_snapshot,
)
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.state import ScreenStatus


def _candidate(ticker: str, signal: int = 70) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        accum_score=50.0,
        rsi=50.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.0,
        current_price=1000,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            rationale="t",
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=signal, strength=SimpleNamespace(value="MODERATE"))
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
        ),
        name=ticker,
    )


def _result(tickers: list[str]) -> SimpleNamespace:
    candidates = [_candidate(t, signal=80 - i) for i, t in enumerate(tickers)]
    projection = SimpleNamespace(
        candidates=candidates,
        window_days=7,
        data_as_of={"latest_candle_date": "2026-07-25"},
        applied_filters=SimpleNamespace(sort_by="signal", top=20),
    )
    return SimpleNamespace(
        single_projection=projection,
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )


def test_refresh_keeps_prior_rows_while_recomputing():
    """Criterion 1: r refresh must not blank a READY board."""

    gate = threading.Event()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        if calls["n"] == 1:
            return _result(["PGEO", "INDF"])
        gate.wait(timeout=5.0)
        return _result(["BBCA", "BBRI", "TLKM"])

    controller = BoardController(loader)

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=loader,
            accum_controller=controller,
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(60):
                await pilot.pause(0.05)
                if app._stage == "accum" and len(app._rows) == 2:
                    break
            assert app._stage == "accum"
            assert [r.ticker for r in app._rows] == ["PGEO", "INDF"]
            prior = list(app._rows)

            app.action_refresh_local()
            await pilot.pause(0.05)
            # Still showing prior board while second load blocked
            assert app._recomputing is True
            assert app._stage == "accum"
            assert [r.ticker for r in app._rows] == [r.ticker for r in prior]
            assert "recomputing" in app._status_note

            gate.set()
            for _ in range(80):
                await pilot.pause(0.05)
                if not app._recomputing and len(app._rows) == 3:
                    break
            assert app._recomputing is False
            assert app._board_source == "live"
            assert [r.ticker for r in app._rows] == ["BBCA", "BBRI", "TLKM"]

    asyncio.run(scenario())


def test_stale_generation_cannot_clobber_newer_ready():
    """Criterion 2: tracker generation rejection still holds with retained payload."""
    from src.adapters.tui.state import ScreenStateTracker

    tracker = ScreenStateTracker()
    g1 = tracker.begin()
    assert tracker.complete_current(g1, payload={"v": 1}) is True
    assert tracker.state.status is ScreenStatus.READY
    assert tracker.state.payload == {"v": 1}

    g2 = tracker.begin()
    # LOADING retains prior READY payload
    assert tracker.state.status is ScreenStatus.LOADING
    assert tracker.state.payload == {"v": 1}

    # Stale g1 delivery rejected
    assert tracker.complete_current(g1, payload={"v": "stale"}) is False
    assert tracker.state.payload == {"v": 1}

    assert tracker.complete_current(g2, payload={"v": 2}) is True
    assert tracker.state.payload == {"v": 2}
    assert tracker.state.status is ScreenStatus.READY


def test_open_restores_snapshot_before_slow_loader(tmp_path: Path):
    """Criterion 3–4: planted snapshot paints immediately; live recompute replaces it."""

    payload = _result(["SNAP1", "SNAP2"])
    view = AccumPresenter().present(payload)
    identity = identity_from_live_payload(payload, view, universe="lq45")
    snap_path = tmp_path / "tui_last_accum_board.json"
    write_accum_board_snapshot(snap_path, snapshot_from_board_view(view, identity))

    gate = threading.Event()
    live_payload = _result(["LIVE1"])

    def slow_loader():
        gate.wait(timeout=5.0)
        return live_payload

    controller = BoardController(slow_loader)

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=slow_loader,
            accum_controller=controller,
            accum_presenter=AccumPresenter(),
            board_snapshot_path=snap_path,
            snapshot_universe="lq45",
        )
        async with app.run_test(size=(140, 36)) as pilot:
            # Snapshot should paint without waiting on gate
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and len(app._rows) >= 2:
                    break
            assert app._stage == "accum"
            assert app._board_source == "snapshot"
            assert [r.ticker for r in app._rows] == ["SNAP1", "SNAP2"]
            assert "snapshot" in app._snapshot_freshness
            assert "recomputing" in app._status_note
            assert app._recomputing is True  # live recompute in flight

            gate.set()
            for _ in range(80):
                await pilot.pause(0.05)
                if app._board_source == "live" and not app._recomputing:
                    break
            assert app._board_source == "live"
            assert [r.ticker for r in app._rows] == ["LIVE1"]
            # Successful live run rewrote snapshot for next open
            assert snap_path.is_file()
            text = snap_path.read_text(encoding="utf-8")
            assert "LIVE1" in text
            assert "SNAP1" not in text

    asyncio.run(scenario())


def test_successful_load_writes_snapshot(tmp_path: Path):
    """Criterion 4: live READY updates snapshot file via real paint path."""
    result = _result(["WRIT1", "WRIT2"])
    path = tmp_path / "out.json"
    controller = BoardController(lambda: result)

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_controller=controller,
            accum_presenter=AccumPresenter(),
            board_snapshot_path=path,
            snapshot_universe="lq45",
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(60):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._board_source == "live":
                    break
            assert path.is_file()
            assert "WRIT1" in path.read_text(encoding="utf-8")

    asyncio.run(scenario())
