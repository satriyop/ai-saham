"""Judge desk Verdict mast layout (present-only; no re-score)."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
    present_accum_engine_inspect,
)
from src.adapters.tui.presenters.accum_presenter import AccumRowView


def _row_with_source(*, action: str = "WATCH", gate: str = "OPEN") -> AccumRowView:
    source = SimpleNamespace(
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
            action=SimpleNamespace(value=action, short=action),
            signal_score=84,
            signal_strength=SimpleNamespace(value="MODERATE"),
            rationale=f"Signal 84 · {action}",
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
            risk_level_name="OPEN" if gate == "OPEN" else "BLOCKED",
        ),
        risk_gate_evaluations=(),
    )
    return AccumRowView(
        ticker="BBCA",
        signal="84",
        accum="48.2",
        action=action,
        phase="COMPRESSION",
        streak="2",
        rsi="50",
        net_pct="0.5",
        disc_pct="0",
        price="6275",
        gate=gate,
        name="BBCA",
        source=source,
    )


def test_verdict_mast_leads_with_action_and_gate():
    view = present_accum_engine_inspect(_row_with_source(action="WATCH", gate="OPEN"))
    text = view.text
    assert "Verdict mast" in text
    assert "WATCH" in text
    assert "Gate" in text and "OPEN" in text
    assert "Judgment · Verdict mast" in text
    assert "Why" in text
    assert "present-only" in text.lower()
    assert "re-score" not in text.lower() or "not a re-score" in text.lower()


def test_verdict_mast_enter_and_avoid_show_action():
    for action, gate in (("ENTER", "OPEN"), ("AVOID", "BLOCK")):
        view = present_accum_engine_inspect(_row_with_source(action=action, gate=gate))
        assert action in view.text
        assert "Gate" in view.text


def test_verdict_mast_phase_timeline_with_facts():
    facts = (
        PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
        PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
    )
    view = present_accum_engine_inspect(
        _row_with_source(),
        phase_sequence=facts,
    )
    text = view.text
    assert "Phase sequence" in text
    assert "ACCUMULATION → COMPRESSION" in text
    assert "2026-07-20" in text
    assert "timeline" in text.lower() or "ledger" in text.lower()
    assert "now" in text.lower() and "COMPRESSION" in text


def test_limited_judge_still_verdict_mast_without_inventing_ready():
    row = AccumRowView(
        ticker="ASII",
        signal="40",
        accum="30",
        action="AVOID",
        phase="NONE",
        streak="0",
        rsi="60",
        net_pct="0",
        disc_pct="0",
        price="5000",
        gate="BLOCKED",
        source=None,
    )
    view = present_accum_engine_inspect(row)
    assert view.limited is True
    assert "Limited judge" in view.text or "limited" in view.text.lower()
    assert "Verdict mast" in view.text
    assert "AVOID" in view.text
