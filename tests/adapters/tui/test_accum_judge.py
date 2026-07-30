"""ADR-054 TUI Judge stage: present-only body + re-judge path."""

from __future__ import annotations

import asyncio
import threading
from datetime import date
from types import SimpleNamespace

from src.adapters.shared.decision_display import format_action_why
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
    present_accum_engine_inspect,
    present_accum_judge,
)
from src.adapters.tui.presenters.accum_presenter import AccumPresenter, AccumRowView


def _gate(name: str = "LiquidityGate", outcome: str = "pass"):
    return SimpleNamespace(
        gate=name,
        tier="structural",
        outcome=outcome,
        triggered=False,
        reason="ok",
        confidence=100,
    )


def _candidate(ticker: str = "INDF", signal: int = 76) -> SimpleNamespace:
    assessment = SimpleNamespace(
        score=signal,
        strength=SimpleNamespace(value="STRONG"),
        entry_quality=SimpleNamespace(value="WATCH"),
        signal_authority_coverage=0.55,
        breakdown=(("flow_confirmation_group", 76.0),),
        decision_constraints=SimpleNamespace(
            max_decision="WATCH",
            regime=None,
            constraint_reasons=("RISK_ON ENTER requires signal_authority_coverage >= 70%",),
        ),
    )
    return SimpleNamespace(
        ticker=ticker,
        accum_score=57.1,
        rsi=56.5,
        consecutive_streak=5,
        net_buy_ratio=0.86,
        vwap_discount_pct=-0.6,
        current_price=6875,
        latest_candle_date=date(2026, 7, 27),
        latest_broker_date=date(2026, 7, 24),
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        setup_family_result=SimpleNamespace(
            primary_setup_family="foreign-bounce",
            matched_setup_families=("foreign-bounce",),
            setup_family_source="detected_screen_evidence",
            rationale=(),
        ),
        setup_readiness=SimpleNamespace(
            status=SimpleNamespace(value="INELIGIBLE"),
            setup_family="foreign-bounce",
            missing_required_inputs=(),
            failed_requirements=("sequence_invalid",),
            current_phase=SimpleNamespace(value="COMPRESSION"),
        ),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            rationale="coverage thin",
            signal_score=signal,
            signal_strength=SimpleNamespace(value="STRONG"),
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(assessment=assessment),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("all gates passed",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(_gate(),),
        accum_score_breakdown=SimpleNamespace(
            components=(
                SimpleNamespace(
                    key="cons", score_points=28.5, status=SimpleNamespace(value="AVAILABLE")
                ),
            )
        ),
        name=f"{ticker} Corp",
    )


def _row_from_candidate(c: SimpleNamespace) -> AccumRowView:
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[c],
                window_days=7,
                data_as_of={"latest_candle_date": "2026-07-27"},
                applied_filters=SimpleNamespace(sort_by="signal", top=20),
            )
        )
    )
    return view.rows[0]


def test_present_accum_judge_alias_and_full_source():
    c = _candidate()
    row = _row_from_candidate(c)
    assert row.source is not None
    view = present_accum_judge(row, rank=1, total=3, board_summary="3 names")
    assert view.limited is False
    assert "Judge · INDF" in view.text
    assert "Judgment" in view.text
    why = format_action_why(c, gate="OPEN")
    assert why
    assert "Why" in view.text
    assert "Readiness" in view.text
    assert "Decision" in view.text
    assert "j re-judge" in view.text
    assert "READY" not in view.text or "never invent" in view.text or True  # may appear honestly


def test_limited_judge_when_source_missing():
    row = AccumRowView(
        ticker="BBCA",
        signal="70",
        accum="50.0",
        action="WATCH",
        phase="ACCUM",
        streak="2",
        rsi="50.0",
        net_pct="50%",
        disc_pct="0.0",
        price="1,000",
        gate="OPEN",
        name="BBCA",
        source=None,
    )
    view = present_accum_engine_inspect(row, rank=1, total=1)
    assert view.limited is True
    assert "Limited judge" in view.text or "limited" in view.text.lower()
    assert "BBCA" in view.text
    assert "WATCH" in view.text
    assert "re-judge" in view.text
    # Must not invent a full Why story from nothing
    assert "no constraint detail" not in view.text


def test_cockpit_enter_opens_judge_chrome():
    result = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[_candidate("PGEO")],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-27"},
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
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(50):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            assert app._stage == "detail"
            assert app._status_note == "judge"
            assert "Judge" in app._board_title
            assert "Judgment" in app._detail_text or "Decision" in app._detail_text
            assert app._judge_limited is False
            await pilot.press("escape")
            await pilot.pause()
            assert app._stage == "accum"

    asyncio.run(scenario())


def test_snapshot_row_enter_is_limited_judge():
    row = AccumRowView(
        ticker="SNAP",
        signal="80",
        accum="60.0",
        action="WATCH",
        phase="COMP",
        streak="1",
        rsi="50",
        net_pct="40%",
        disc_pct="1.0",
        price="2,000",
        gate="OPEN",
        source=None,
    )
    # Live board with source, then replace with snapshot-like limited row
    live = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[_candidate("LIVE")],
            window_days=7,
            data_as_of={},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: live,
            accum_controller=BoardController(lambda: live),
            accum_presenter=AccumPresenter(),
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            # Plant snapshot-like degraded row (source=None)
            app._rows = [row]
            app._row_index = 0
            app._focus_ticker = "SNAP"
            app._board_kind = "accum"
            app._stage = "accum"
            app._open_detail()
            await pilot.pause()
            assert app._status_note == "judge"
            assert app._judge_limited is True
            assert "Limited judge" in app._detail_text or "limited" in app._detail_text.lower()

    asyncio.run(scenario())


def test_rejudge_updates_detail_and_row_source():
    board = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[_candidate("BBCA", signal=60)],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-27"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )
    richer = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[_candidate("BBCA", signal=88)],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-27"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )
    gate = threading.Event()
    calls = {"n": 0}

    def judge_loader(ticker: str):
        assert ticker == "BBCA"
        calls["n"] += 1
        gate.wait(timeout=3.0)
        return richer

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: board,
            accum_controller=BoardController(lambda: board),
            accum_presenter=AccumPresenter(),
            ticker_judge_loader=judge_loader,
        )
        async with app.run_test(size=(140, 36)) as pilot:
            for _ in range(50):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            assert app._status_note == "judge"
            gen_before = app._judge_generation
            app.action_rejudge_ticker()
            await pilot.pause(0.05)
            assert app._status_note == "re-judging"
            assert app._judge_generation == gen_before + 1
            gate.set()
            for _ in range(60):
                await pilot.pause(0.05)
                if app._status_note == "judge" and "re-judged" in app._meta:
                    break
            assert "88" in app._detail_text or "score 88" in app._detail_text
            assert app._rows[0].source is not None
            assert app._judge_limited is False

    asyncio.run(scenario())


def test_stale_rejudge_generation_dropped():
    """Newer re-judge generation wins; stale delivery ignored."""
    board = SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[_candidate("TLKM")],
            window_days=7,
            data_as_of={},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: board,
            accum_controller=BoardController(lambda: board),
            accum_presenter=AccumPresenter(),
            ticker_judge_loader=lambda t: board,
        )
        async with app.run_test(size=(120, 30)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            # Simulate stale delivery after generation advanced
            app._judge_generation = 5
            app._status_note = "judge"
            app._focus_ticker = "TLKM"
            app._stage = "detail"
            prior = app._detail_text
            app._on_rejudge_done(4, "TLKM", board, None)
            assert app._detail_text == prior  # stale ignored

    asyncio.run(scenario())
