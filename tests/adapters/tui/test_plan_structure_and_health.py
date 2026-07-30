"""TUI plan structure multi-line body + local cache health rail."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from src.adapters.tui.local_cache_health import (
    assess_local_cache_health,
    format_sidebar_cache_line,
    format_sidebar_next_line,
    load_local_cache_health,
)
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.plan_structure_result import PlanStructureResult, structure_lines
from src.adapters.tui.presenters.plan_stage_presenter import present_plan_stage


def test_structure_lines_show_geometry_and_inherit_copy():
    result = PlanStructureResult(
        summary="structure WATCH · entry 4,825 · stop 4,600 · target 5,275 · 2 lots · no order",
        ticker="BBRI",
        action="WATCH",
        entry="4,825",
        stop="4,600",
        target="5,275",
        lots="2",
        incomplete_reason="",
        plan_id_short="abcd1234",
        inherits_action=True,
        no_order=True,
    )
    text = "\n".join(structure_lines(result))
    assert "Entry" in text and "4,825" in text
    assert "Stop" in text and "4,600" in text
    assert "Target" in text and "5,275" in text
    assert "Lots" in text and "2" in text
    assert "inherited" in text.lower() or "inherits" in text.lower()
    assert "no broker order" in text.lower()
    assert "abcd1234" in text
    # Values come from result fields, not a hard-coded demo constant list alone
    assert result.entry in text and result.stop in text


def test_structure_incomplete_capital_message():
    result = PlanStructureResult(
        summary="structure WATCH · no capital · no order",
        action="WATCH",
        incomplete_reason="no capital · set swing.capital in user.yaml or CLI --capital",
        inherits_action=True,
        no_order=True,
    )
    text = "\n".join(structure_lines(result)).lower()
    assert "no capital" in text
    assert "no broker order" in text
    assert "entry" in text  # still lists entry line as —


def test_present_plan_stage_uses_structure_not_invented_action():
    view = present_plan_stage(
        SimpleNamespace(
            ticker="BBCA",
            signal="73",
            accum="61",
            action="ENTER",
            gate="OPEN",
            source=None,
        ),
        ticker="BBCA",
        source="Screen · accumulation",
        structure=PlanStructureResult(
            summary="structure ENTER · entry 6,225 · 3 lots · no order",
            action="ENTER",
            entry="6,225",
            stop="5,900",
            target="6,800",
            lots="3",
            inherits_action=True,
            no_order=True,
        ),
        running=False,
    )
    text = view.text
    assert "6,225" in text and "5,900" in text and "6,800" in text
    assert "3" in text
    assert "inherits" in text.lower() or "inherited" in text.lower()
    assert "no broker order" in text.lower()
    assert "re-score" not in text.lower()
    assert "re-check" not in text.lower()
    # Board judgment action preserved
    assert "ENTER" in text


def test_assess_local_cache_health_empty_and_lag():
    empty = assess_local_cache_health(universe="lq45", candle_latest=None, broker_latest=None)
    assert empty.status == "empty"
    assert "fetch" in empty.next_step.lower()
    assert "empty" in format_sidebar_cache_line(empty).lower()

    lag = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 20),
        lag_days=1,
    )
    assert lag.status == "lag"
    line = format_sidebar_cache_line(lag)
    assert "2026-07-28" in line
    assert "2026-07-20" in line
    assert "LAG" in line
    next_s = format_sidebar_next_line(lag).lower()
    assert "fetch" in next_s or "stale" in next_s

    ready = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 28),
    )
    assert ready.status == "ready"
    assert "explicit" in format_sidebar_next_line(ready).lower()


def test_load_local_cache_health_uses_callables_only():
    health = load_local_cache_health(
        universe="lq45",
        get_candle_latest=lambda: date(2026, 7, 25),
        get_broker_latest=lambda: date(2026, 7, 24),
    )
    assert health.candle_as_of == "2026-07-25"
    assert health.broker_as_of == "2026-07-24"
    assert health.status in {"ready", "lag"}


def test_load_local_cache_health_both_none_is_empty_not_unknown():
    health = load_local_cache_health(
        universe="lq45",
        get_candle_latest=lambda: None,
        get_broker_latest=lambda: None,
    )
    assert health.status == "empty"
    assert "empty" in format_sidebar_cache_line(health).lower()


def test_load_local_cache_health_both_raise_is_unknown():
    def boom():
        raise RuntimeError("db locked")

    health = load_local_cache_health(
        universe="lq45",
        get_candle_latest=boom,
        get_broker_latest=boom,
    )
    assert health.status == "unknown"


def test_cockpit_plan_stage_shows_multiline_structure():
    async def scenario() -> None:
        app = CockpitApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._focus_ticker = "BBRI"
            app._stage = "accum"
            app._board_kind = "accum"
            app._rows = [
                SimpleNamespace(
                    ticker="BBRI",
                    signal="72",
                    accum="50.0",
                    action="WATCH",
                    gate="OPEN",
                    source=None,
                )
            ]
            app._row_index = 0
            planned: list[str] = []

            def runner(t: str):
                planned.append(t)
                return PlanStructureResult(
                    summary=(
                        "structure WATCH · entry 4,825 · stop 4,600 · "
                        "target 5,275 · 2 lots · no order"
                    ),
                    ticker=t,
                    action="WATCH",
                    entry="4,825",
                    stop="4,600",
                    target="5,275",
                    lots="2",
                    inherits_action=True,
                    no_order=True,
                )

            app._plan_runner = runner
            app._run_command("plan-swing")
            for _ in range(50):
                await pilot.pause(0.05)
                if planned and not app._plan_running:
                    break
            assert planned == ["BBRI"]
            assert app._stage == "plan"
            assert app._plan_structure is not None
            assert app._plan_structure.entry == "4,825"
            body = app._plan_body_text()
            assert "Entry" in body and "4,825" in body
            assert "Stop" in body and "4,600" in body
            assert "Target" in body and "5,275" in body
            assert "Lots" in body
            assert "inherited" in body.lower() or "inherits" in body.lower()
            assert "no broker order" in body.lower()

    asyncio.run(scenario())


def test_cockpit_paints_cache_health_on_mount():
    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 27),
    )

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.1)
            assert app._cache_health is not None
            cache_text = str(app.query_one("#side-cache").render())
            # Sidebar should mention candle/broker dates or lag
            assert "2026-07-28" in cache_text or "candle" in cache_text.lower()
            online = str(app.query_one("#side-online").render())
            assert online  # next-step cue present

    asyncio.run(scenario())


def test_focus_change_does_not_clobber_session_cache_health():
    """After board evidence update, #side-cache still shows session health."""
    from src.adapters.tui.controllers.board_controller import BoardController
    from src.adapters.tui.presenters.accum_presenter import AccumPresenter

    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 28),
    )
    c = SimpleNamespace(
        ticker="BBCA",
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
            assessment=SimpleNamespace(score=70, strength=SimpleNamespace(value="MODERATE"))
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
        ),
        name="BBCA",
        latest_candle_date=date(2026, 7, 20),
        latest_broker_date=date(2026, 7, 10),
        freshness=SimpleNamespace(
            candle_as_of=date(2026, 7, 20),
            broker_as_of=date(2026, 7, 10),
            alignment_state=SimpleNamespace(value="LAG"),
        ),
    )
    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-20"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: result,
            accum_controller=BoardController(lambda: result),
            accum_presenter=AccumPresenter(),
            cache_health_loader=lambda: health,
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(50):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            # Focus path that used to overwrite Cache with row lag "—"
            app._update_accum_evidence()
            await pilot.pause(0.05)
            cache_text = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in cache_text
            assert "candle" in cache_text.lower()
            # Must not be the bare lag placeholder that focus used to write
            assert cache_text.strip() != "Cache    —"

    asyncio.run(scenario())


def test_empty_health_cues_fetch_on_empty_stage():
    health = assess_local_cache_health(universe="lq45", candle_latest=None, broker_latest=None)

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._show_empty()
            await pilot.pause(0.05)
            footer = app._footer_hint().lower()
            assert "fetch" in footer
            cache_text = str(app.query_one("#side-cache").render()).lower()
            assert "empty" in cache_text
            assert "no cache" in app._mode.lower()

    asyncio.run(scenario())


def test_empty_stage_with_ready_health_keeps_candle_broker_dates():
    """0-candidate / empty board must not hardcode Cache empty over ready health."""
    from src.adapters.tui.state import ScreenState, ScreenStatus

    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 27),
    )

    async def scenario() -> None:
        app = CockpitApp(cache_health_loader=lambda: health)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            # Mount path already painted ready health
            before = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in before
            assert "candle" in before.lower()

            # Empty board stage via the real EMPTY screen path (not past chrome)
            app._on_accum_state(
                ScreenState(
                    generation=1,
                    status=ScreenStatus.EMPTY,
                    payload=None,
                )
            )
            await pilot.pause(0.05)
            assert app._stage == "empty"
            cache_text = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in cache_text
            assert "2026-07-27" in cache_text
            assert "candle" in cache_text.lower()
            assert "Cache    empty" not in cache_text
            assert cache_text.strip().lower() != "cache    empty"
            # Mode must not dishonestly claim no cache while health is ready
            assert "no cache" not in app._mode.lower()
            assert "local-first" in app._mode.lower()

            # Direct _show_empty also keeps health paint (not clobber)
            app._show_empty()
            await pilot.pause(0.05)
            after = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in after
            assert "Cache    empty" not in after
            assert "no cache" not in app._mode.lower()

    asyncio.run(scenario())


def test_fetch_done_online_note_survives_health_paint():
    health = assess_local_cache_health(
        universe="lq45",
        candle_latest=date(2026, 7, 28),
        broker_latest=date(2026, 7, 28),
    )

    async def scenario() -> None:
        app = CockpitApp(
            cache_health_loader=lambda: health,
            fetch_runner=lambda: None,
        )
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._on_fetch_done()
            await pilot.pause(0.05)
            online = str(app.query_one("#side-online").render())
            assert "Last fetch ok" in online
            cache_text = str(app.query_one("#side-cache").render())
            assert "2026-07-28" in cache_text

    asyncio.run(scenario())
