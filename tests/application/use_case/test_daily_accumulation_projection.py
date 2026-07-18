"""Tests for DailyAccumulationProjector — canonical accumulation projection."""

from decimal import Decimal
from types import SimpleNamespace

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.use_case.daily_accumulation_projection import (
    DailyAccumulationProjector,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.domain.value_objects.trade_setup import SetupAction


def _make_candidate(ticker: str, foreign_flow_score: float = 50.0) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("10000"),
        current_price=Decimal("10050"),
        vwap_discount_pct=0.5,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=foreign_flow_score,
        top_brokers=None,
        institutional_flag=True,
    )


def _with_signal(candidate: AccumulationCandidate, score: int, signal_authority_coverage: float):
    assessment = SimpleNamespace(score=score, signal_authority_coverage=signal_authority_coverage)
    candidate.signal_assessment = SimpleNamespace(assessment=assessment)
    return candidate


def _with_risk(candidate: AccumulationCandidate, gate_triggered: str | None):
    candidate.risk_assessment = SimpleNamespace(gate_triggered=gate_triggered)
    return candidate


def _with_trade_setup(candidate: AccumulationCandidate, action: SetupAction):
    candidate.trade_setup = SimpleNamespace(action=action)
    return candidate


def _with_setup_phase(candidate: AccumulationCandidate, phase: SetupPhaseState):
    candidate.setup_phase = SimpleNamespace(current_phase=phase)
    return candidate


def test_projection_preserves_input_order():
    low = _with_trade_setup(_make_candidate("LOW_ACTION", 10.0), SetupAction.AVOID)
    high = _with_trade_setup(_make_candidate("HIGH_ACTION", 90.0), SetupAction.ENTER)

    projection = DailyAccumulationProjector().project(
        candidates=[low, high], checked=2, data_ready=2
    )

    assert [c.ticker for c in projection.candidates] == ["LOW_ACTION", "HIGH_ACTION"]


def test_projection_uses_canonical_trade_setup_action():
    candidate = _with_trade_setup(_make_candidate("INDF"), SetupAction.WATCH)

    projection = DailyAccumulationProjector().project(
        candidates=[candidate], checked=1, data_ready=1
    )

    assert projection.candidates[0].action == "WATCH"


def test_missing_trade_setup_is_unclassified_not_review():
    candidate = _make_candidate("BBTN")
    assert candidate.trade_setup is None

    projection = DailyAccumulationProjector().project(
        candidates=[candidate], checked=1, data_ready=1
    )

    assert projection.candidates[0].action is None
    assert projection.summary.unclassified_count == 1
    assert any("missing" in w.lower() and "canonical" in w.lower() for w in projection.warnings)
    assert "REVIEW" not in " ".join(projection.warnings)
    assert all(c.action != "REVIEW" for c in projection.candidates)


def test_summary_counts_enter_watch_blocked_unclassified():
    enter = _with_trade_setup(_make_candidate("ENTER1"), SetupAction.ENTER)
    watch = _with_trade_setup(_make_candidate("WATCH1"), SetupAction.WATCH)
    blocked_exec = _with_trade_setup(_make_candidate("BLOCK1"), SetupAction.BLOCKED_EXECUTION)
    blocked_struct = _with_trade_setup(_make_candidate("BLOCK2"), SetupAction.BLOCKED_STRUCTURAL)
    missing = _make_candidate("MISSING1")

    projection = DailyAccumulationProjector().project(
        candidates=[enter, watch, blocked_exec, blocked_struct, missing],
        checked=5,
        data_ready=5,
    )

    assert projection.summary.enter_count == 1
    assert projection.summary.watch_count == 1
    assert projection.summary.blocked_count == 2
    assert projection.summary.unclassified_count == 1
    assert projection.summary.flow_candidates == 5


def test_projection_carries_signal_risk_and_phase_fields():
    candidate = _make_candidate("GOTO", foreign_flow_score=77.3)
    candidate = _with_signal(candidate, score=61, signal_authority_coverage=0.64)
    candidate = _with_risk(candidate, gate_triggered="liquidity_gate")
    candidate = _with_setup_phase(candidate, SetupPhaseState.EXHAUSTION)
    candidate = _with_trade_setup(candidate, SetupAction.AVOID)

    projection = DailyAccumulationProjector().project(
        candidates=[candidate], checked=1, data_ready=1
    )

    projected = projection.candidates[0]
    assert projected.flow_score == 77.3
    assert projected.signal_score == 61
    assert projected.signal_authority_coverage == 0.64
    assert projected.risk_status == "BLOCK"
    assert projected.setup_phase == "EXHAUSTION"
    assert projected.action == "AVOID"


def test_daily_projection_contract():
    # Test A: Daily Projection Contract
    candidate = _make_candidate("GOTO")
    candidate = _with_signal(candidate, score=61, signal_authority_coverage=0.64)
    projection = DailyAccumulationProjector().project(
        candidates=[candidate], checked=1, data_ready=1
    )
    projected = projection.candidates[0]
    assert projected.signal_authority_coverage == 0.64
    assert not hasattr(projected, "coverage_score")


def test_daily_missing_assessment():
    # Test B: Daily Missing Assessment
    candidate = _make_candidate("GOTO")
    assert candidate.signal_assessment is None
    projection = DailyAccumulationProjector().project(
        candidates=[candidate], checked=1, data_ready=1
    )
    projected = projection.candidates[0]
    assert projected.signal_authority_coverage is None
