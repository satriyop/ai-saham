"""Judge desk paint contract — pure model (no full-app mount).

Journey Enter → judge → d → esc residual: D3 (accum_judge / e2e smoke).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.tui.judge_desk_model import build_judge_desk_model
from src.adapters.tui.phase_sequence import PhaseSequenceFact
from src.adapters.tui.presenters.accum_presenter import AccumRowView
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


def _row() -> AccumRowView:
    return AccumRowView(
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


def test_build_judge_desk_model_has_verdict_fields():
    model = build_judge_desk_model(
        _row(),
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


def test_action_css_class_blocked_struct_is_coral():
    from src.adapters.tui.judge_desk_model import action_css_class

    assert action_css_class("ENTER") == "action-enter"
    assert action_css_class("WATCH") == "action-watch"
    assert action_css_class("BLOCKED(struct)") == "action-avoid"
    assert action_css_class("BLOCKED") == "action-avoid"


def test_score_ready_label_no_midword_clip():
    from src.adapters.tui.judge_desk_model import _score_ready_label

    assert _score_ready_label("flow-only (setup readiness not applicable)") == "flow-only"
    assert _score_ready_label("— (no candidate object)") == "no object"
    short = _score_ready_label("PARTIAL")
    assert short == "PARTIAL"
    long = _score_ready_label("x" * 40)
    assert long.endswith("…") and len(long) <= 14


def test_phase_arrow_marks_current_brass():
    from src.adapters.tui.widgets.judge_desk import _format_phase_arrow

    rendered = _format_phase_arrow("ACCUMULATION → COMPRESSION")
    assert "ACCUMULATION" in rendered
    assert "COMPRESSION" in rendered
    assert "#d4b06a" in rendered  # current node brass
    assert "→" in rendered
    solo = _format_phase_arrow("NONE")
    assert "NONE" in solo and "#d4b06a" in solo


def test_judge_paint_contract_mast_flags_and_compact_default():
    """What #jd-action / #jd-gate / flags paint — compact until detail · d."""
    model = build_judge_desk_model(
        _row(),
        phase_sequence=(
            PhaseSequenceFact(phase="ACCUMULATION", as_of="2026-07-20"),
            PhaseSequenceFact(phase="COMPRESSION", as_of="2026-07-28"),
        ),
    )
    title = f"Judge · {model.ticker}"
    assert "BBCA" in title
    assert model.action == "WATCH"
    assert model.gate == "OPEN"
    assert model.phase_arrow
    assert "ACCUMULATION" in model.phase_arrow or "→" in model.phase_arrow

    # Expandable flags for chip row (detail · d master + named panels)
    desk = JudgeDesk()
    expandable = desk._available_expandable_flags(model)
    assert "phase_plus" in expandable
    if model.decision_lines:
        assert "stack" in expandable

    # Compact mode: decision stack waits for d / stack chip
    # Primary cards always present in model; secondary gated at paint time
    primary = frozenset({"risk", "trade_setup", "accum", "data"})
    card_keys = {c.key for c in model.cards}
    assert primary & card_keys or model.limited
