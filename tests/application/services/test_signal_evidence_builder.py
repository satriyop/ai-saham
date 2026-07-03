"""Tests for SignalEvidenceBuilder (Phase 1 — evidence beside scores)."""

from __future__ import annotations

from datetime import date

from src.application.services.signal_evidence_builder import SignalEvidenceBuilder
from src.application.use_case.assess_signal_use_case import (
    AssessSignalRequest,
    AssessSignalUseCase,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.signal_assessment import SignalContext

_ALL_FACTOR_NAMES = {
    "bandar_intensity",
    "foreign_flow_quality",
    "insider_activity",
    "seasonality_edge",
    "analyst_consensus",
    "forward_valuation",
}


def _build(context: SignalContext):
    """Run scoring then annotate with evidence."""
    response = AssessSignalUseCase().execute(
        AssessSignalRequest(ticker=context.ticker, signal_context=context)
    )
    breakdown = response.assessment.breakdown
    return SignalEvidenceBuilder().build(context, breakdown)


def _factor_by_name(evidence, name):
    return next(f for f in evidence.factors if f.name == name)


def _complete_context(**overrides) -> SignalContext:
    base = dict(
        ticker="TEST",
        snapshot_date=date(2026, 7, 3),
        bandar_broad_score=8,
        bandar_max_range=12,
        foreign_flow_quality=0.85,
        insider_net_buy_ratio=0.6,
        seasonality_win_rate=60.0,
        seasonality_avg_return_pct=1.2,
        seasonality_total_years=5,
        seasonality_back_years=5,
        analyst_buy_pct=0.8,
        analyst_upside_pct=15.0,
        forward_pe=12.0,
    )
    base.update(overrides)
    return SignalContext(**base)


def test_complete_evidence_all_present():
    ev = _build(_complete_context())
    assert len(ev.factors) == 6
    assert all(f.freshness is Freshness.FRESH for f in ev.factors)
    assert ev.coverage_ratio == 1.0
    assert ev.aggregate_confidence == 1.0
    assert ev.missing_factors == ()


def test_no_evidence_all_missing():
    ctx = SignalContext(ticker="TEST", snapshot_date=date(2026, 7, 3))
    ev = _build(ctx)
    assert len(ev.factors) == 6
    assert all(f.freshness is Freshness.MISSING for f in ev.factors)
    assert ev.coverage_ratio == 0.0
    assert ev.aggregate_confidence == 0.0
    assert set(ev.missing_factors) == _ALL_FACTOR_NAMES


def test_partial_evidence_three_present():
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=date(2026, 7, 3),
        bandar_broad_score=8,
        bandar_max_range=12,
        foreign_flow_quality=0.85,
        analyst_buy_pct=0.8,
        analyst_upside_pct=15.0,
    )
    ev = _build(ctx)
    assert ev.coverage_ratio == 0.5
    assert ev.aggregate_confidence == 1.0
    assert set(ev.missing_factors) == {
        "insider_activity",
        "seasonality_edge",
        "forward_valuation",
    }
    present = {f.name for f in ev.factors if f.freshness is not Freshness.MISSING}
    assert present == {
        "bandar_intensity",
        "foreign_flow_quality",
        "analyst_consensus",
    }


def test_seasonality_raw_fields_includes_total_years():
    ctx = _complete_context(seasonality_total_years=7)
    ev = _build(ctx)
    seasonality = _factor_by_name(ev, "seasonality_edge")
    assert ("total_years", "7") in seasonality.raw_fields


def test_seasonality_with_less_than_five_years_is_missing():
    ctx = _complete_context(seasonality_total_years=4)
    ev = _build(ctx)
    seasonality = _factor_by_name(ev, "seasonality_edge")
    assert seasonality.freshness is Freshness.MISSING
    assert seasonality.direction is Direction.NEUTRAL
    assert "seasonality_edge" in ev.missing_factors


def test_seasonality_with_unknown_years_is_missing():
    ctx = _complete_context(seasonality_total_years=None, seasonality_back_years=None)
    ev = _build(ctx)
    seasonality = _factor_by_name(ev, "seasonality_edge")
    assert seasonality.freshness is Freshness.MISSING
    assert seasonality.direction is Direction.NEUTRAL
    assert "seasonality_edge" in ev.missing_factors


def test_missing_factor_direction_is_neutral():
    ctx = SignalContext(ticker="TEST", snapshot_date=date(2026, 7, 3))
    ev = _build(ctx)
    for f in ev.factors:
        assert f.freshness is Freshness.MISSING
        assert f.direction is Direction.NEUTRAL


def test_high_score_direction_bullish():
    # foreign_flow_quality=0.9 → component_score 90 → bullish
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=date(2026, 7, 3),
        foreign_flow_quality=0.9,
    )
    ev = _build(ctx)
    foreign = _factor_by_name(ev, "foreign_flow_quality")
    assert foreign.strength >= 0.6
    assert foreign.direction is Direction.BULLISH


def test_low_score_direction_bearish():
    # foreign_flow_quality=0.1 → component_score 10 → bearish
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=date(2026, 7, 3),
        foreign_flow_quality=0.1,
    )
    ev = _build(ctx)
    foreign = _factor_by_name(ev, "foreign_flow_quality")
    assert foreign.strength <= 0.4
    assert foreign.direction is Direction.BEARISH


def test_deterministic_object_construction():
    # Same inputs produce identical frozen dataclass instances.
    # (True serialization determinism added when to_dict() is implemented in Phase 7.)
    ctx = _complete_context()
    ev1 = _build(ctx)
    ev2 = _build(ctx)
    assert ev1 == ev2


def test_phase1_freshness_is_binary():
    # Phase 1 only emits FRESH or MISSING — STALE requires cache-date info
    # which is not carried by SignalContext until Phase 7.
    from src.domain.value_objects.factor_evidence import Freshness
    ctx_full = _complete_context()
    ctx_empty = SignalContext(ticker="TEST", snapshot_date=date(2026, 7, 3))
    for ctx in (ctx_full, ctx_empty):
        ev = _build(ctx)
        for f in ev.factors:
            assert f.freshness in (Freshness.FRESH, Freshness.MISSING), (
                f"{f.name}: unexpected freshness {f.freshness!r} in Phase 1"
            )


def test_back_years_in_seasonality_raw_fields():
    ctx = _complete_context(seasonality_total_years=5, seasonality_back_years=5)
    ev = _build(ctx)
    seasonality = _factor_by_name(ev, "seasonality_edge")
    assert ("back_years", "5") in seasonality.raw_fields
