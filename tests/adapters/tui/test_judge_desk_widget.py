"""Visual Judge desk widget (Verdict mast) — not text-only dump."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.adapters.tui.judge_desk_model import build_judge_desk_model
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.presenters.accum_presenter import AccumPresenter, AccumRowView
from src.adapters.tui.widgets.judge_desk import JudgeDesk


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        ticker="BBCA",
        accum_score=48.2,
        rsi=50.0,
        consecutive_streak=2,
        net_buy_ratio=0.5,
        vwap_discount_pct=0.0,
        current_price=6275,
        name="BBCA",
        latest_candle_date=None,
        latest_broker_date=None,
        freshness=None,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            signal_score=84,
            signal_strength=SimpleNamespace(value="MODERATE"),
            rationale="Signal 84",
            blocking_gates=(),
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(
                score=84,
                strength=SimpleNamespace(value="MODERATE"),
                entry_quality=SimpleNamespace(value="WATCH"),
                signal_authority_coverage=0.92,
                breakdown=None,
                decision_constraints=None,
            ),
            setup_readiness=None,
            coverage_warning=None,
            signal_authority_coverage=0.92,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
            risk_level_name="OPEN",
        ),
        risk_gate_evaluations=(),
    )


def _result():
    c = _candidate()
    return SimpleNamespace(
        single_projection=SimpleNamespace(
            candidates=[c],
            window_days=7,
            data_as_of={"latest_candle_date": "2026-07-29"},
            applied_filters=SimpleNamespace(sort_by="signal", top=20),
        ),
        multi_projection=None,
        warnings=(),
        effective_session=None,
        market_context=None,
    )


def test_build_judge_desk_model_has_verdict_fields():
    row = AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action="WATCH",
        phase="COMPRESSION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate="OPEN",
        source=_candidate(),
    )
    model = build_judge_desk_model(
        row,
        phase_sequence=(
            PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
            PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
        ),
    )
    assert model.action == "WATCH"
    assert model.gate == "OPEN"
    assert model.limited is False
    assert any(s.label == "Signal" for s in model.scores)
    assert "ACCUMULATION" in model.phase_arrow and "COMPRESSION" in model.phase_arrow


def test_cockpit_judge_shows_judge_desk_widget_not_only_stage_body():
    live = _result()

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=lambda: live,
            accum_presenter=AccumPresenter(),
            phase_history_loader=lambda t, d: (
                PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
                PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
            ),
        )
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.05)
            app._on_accum_payload(live)
            await pilot.pause(0.05)
            assert app._stage == "accum"
            app._row_index = 0
            app._focus_ticker = app._rows[0].ticker
            app._open_detail()
            await pilot.pause(0.1)
            assert app._status_note == "judge"
            desk = app.query_one("#judge-desk", JudgeDesk)
            assert desk.display is True
            body = app.query_one("#stage-body")
            assert body.display is False
            # Painted mast content
            action = str(app.query_one("#jd-action").render())
            assert "WATCH" in action
            gate = str(app.query_one("#jd-gate").render())
            assert "OPEN" in gate or "Gate" in gate
            mast = app.query_one("#jd-mast")
            assert mast.display is not False
            # CSS classes for semantic action
            assert "action-watch" in action or "WATCH" in action
            classes = set(app.query_one("#jd-action").classes)
            assert "action-watch" in classes or "verdict-action" in classes
            phase_arrow = str(app.query_one("#jd-phase-arrow").render())
            assert "ACCUMULATION" in phase_arrow or "→" in phase_arrow

    asyncio.run(scenario())
