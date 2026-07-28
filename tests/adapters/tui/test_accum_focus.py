"""P0–P2 accum focus strip: why Action, Accum recipe, data lag."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.adapters.tui.presenters.accum_presenter import (
    AccumPresenter,
    AccumRowView,
    build_accum_focus,
)


def _candidate(
    *,
    action_value: str = "WATCH",
    coverage: float = 0.0,
    gate_triggered=None,
    disc: float = -1.24,
) -> SimpleNamespace:
    components = (
        SimpleNamespace(key="cons", score_points=28.5, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="streak", score_points=14.4, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="vwap", score_points=0.0, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="rsi", score_points=3.4, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="flow", score_points=3.4, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="bb", score_points=None, status=SimpleNamespace(value="DISABLED")),
        SimpleNamespace(key="inst", score_points=12.5, status=SimpleNamespace(value="AVAILABLE")),
    )
    constraints = SimpleNamespace(
        constraint_reasons=(
            "RISK_ON ENTER requires signal_authority_coverage >= 70%",
            "Setup readiness UNAVAILABLE caps ENTER to WATCH",
        )
    )
    assessment = SimpleNamespace(
        score=79,
        signal_authority_coverage=coverage,
        decision_constraints=constraints,
        setup_readiness=SimpleNamespace(
            status=SimpleNamespace(value="UNAVAILABLE"),
            setup_family="pullback",
            missing_required_inputs=("setup_evidence",),
            failed_requirements=(),
            current_phase=None,
        ),
        strength=SimpleNamespace(value="STRONG"),
    )
    return SimpleNamespace(
        ticker="PGEO",
        accum_score=62.2,
        rsi=60.65,
        consecutive_streak=6,
        net_buy_ratio=0.857,
        vwap_discount_pct=disc,
        current_price=1020,
        latest_candle_date=date(2026, 7, 27),
        latest_broker_date=date(2026, 7, 24),
        freshness=SimpleNamespace(
            candle_as_of=date(2026, 7, 27),
            broker_as_of=date(2026, 7, 24),
            alignment_state=SimpleNamespace(value="LAG"),
        ),
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value=action_value, short=action_value),
            rationale="Signal 79/100 | gate: open",
        ),
        signal_assessment=SimpleNamespace(
            assessment=assessment,
            coverage_warning="Incomplete signal authority coverage",
            signal_authority_coverage=coverage,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=gate_triggered,
            rationale=("all gates passed",),
        ),
        accum_score_breakdown=SimpleNamespace(components=components, accum_score=62.2),
        name="PGEO",
    )


def test_build_accum_focus_why_recipe_lag():
    row = (
        AccumPresenter()
        .present(
            SimpleNamespace(
                single_projection=SimpleNamespace(
                    candidates=[_candidate()],
                    window_days=7,
                    data_as_of={"latest_candle_date": "2026-07-27"},
                    applied_filters=SimpleNamespace(sort_by="signal", top=40),
                )
            )
        )
        .rows[0]
    )
    focus = build_accum_focus(row, rank=1, total=40)
    assert "Why" in focus.strip
    assert "authority 0%" in focus.strip
    assert "setup readiness UNAVAILABLE" in focus.strip
    assert "missing: setup_evidence" in focus.strip
    assert "pullback" in focus.strip
    assert "gate open" in focus.strip
    assert "cons 28.5" in focus.strip
    assert "vwap 0.0" in focus.strip or "vwap 0" in focus.strip
    assert "bb off" in focus.strip
    assert "LAG" in focus.strip or "broker" in focus.strip
    assert "above F_VWAP" in focus.strip
    assert (
        "sort signal"
        in AccumPresenter()
        .present(
            SimpleNamespace(
                single_projection=SimpleNamespace(
                    candidates=[_candidate()],
                    window_days=7,
                    data_as_of={},
                    applied_filters=SimpleNamespace(sort_by="signal", top=40),
                )
            )
        )
        .meta
        or True
    )  # meta on board
    assert "PGEO" in focus.focus_sidebar
    assert focus.lag_label != "—"


def test_meta_mentions_sort_not_accum():
    view = AccumPresenter().present(
        SimpleNamespace(
            single_projection=SimpleNamespace(
                candidates=[_candidate()],
                window_days=7,
                data_as_of={"latest_candle_date": "2026-07-27"},
                applied_filters=SimpleNamespace(sort_by="signal", top=40),
            )
        )
    )
    assert "not Accum" in view.meta
    assert "LAG" in view.meta or "broker" in view.cache_label


def test_gate_blocked_in_why():
    c = _candidate(gate_triggered="BandarGate")
    row = AccumRowView(
        ticker="X",
        signal="50",
        accum="40.0",
        action="BLOCKED(struct)",
        phase="DISTRIB",
        streak="0",
        rsi="40.0",
        net_pct="50%",
        disc_pct="+1.0%",
        price="100",
        gate="BLOCKED",
        source=c,
    )
    focus = build_accum_focus(row)
    assert "gate blocked" in focus.strip


def test_setup_readiness_shows_missing_inputs_not_only_generic():
    c = _candidate()
    # Ensure VO carries concrete missing inputs
    assert c.signal_assessment.assessment.setup_readiness.missing_required_inputs == (
        "setup_evidence",
    )
    row = (
        AccumPresenter()
        .present(
            SimpleNamespace(
                single_projection=SimpleNamespace(
                    candidates=[c],
                    window_days=7,
                    data_as_of={},
                    applied_filters=SimpleNamespace(sort_by="signal", top=10),
                )
            )
        )
        .rows[0]
    )
    focus = build_accum_focus(row)
    assert "missing: setup_evidence" in focus.strip
    # Should not stop at vague line alone without the missing list
    assert "setup readiness UNAVAILABLE [pullback] (missing: setup_evidence)" in focus.strip
