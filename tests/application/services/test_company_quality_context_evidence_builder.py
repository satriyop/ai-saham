"""Unit tests for CompanyQualityContextEvidenceBuilder and shared scorers.

Covers:
  - all four axes present
  - partial coverage (2 of 4)
  - zero coverage → aggregate None / present_axes empty
  - seasonality cap actually lowers its influence in the aggregate
  - coverage_score correctness
  - shared-scorer extraction is byte-identical to AssessSignalUseCase methods
  - evidence_status is always DIAGNOSTIC; deferred axes are recorded
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
    CompanyQualityContextConfig,
    CompanyQualityContextRequest,
)
from src.application.services import company_quality_scoring as cqs
from src.application.use_case.assess_signal_use_case import AssessSignalUseCase
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.signal_assessment import SignalContext
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)

SNAP = date(2026, 7, 3)


def _ctx(**kwargs) -> SignalContext:
    return SignalContext(ticker="TEST", snapshot_date=SNAP, **kwargs)


def _builder() -> CompanyQualityContextEvidenceBuilder:
    return create_company_quality_context_evidence_builder()


def _build(ctx: SignalContext):
    return _builder().build(
        CompanyQualityContextRequest(
            ticker="TEST", snapshot_date=SNAP, signal_context=ctx
        )
    )


# ── all four axes present ──────────────────────────────────────────────────────

def test_all_four_axes_present():
    ev = _build(_ctx(
        forward_pe=8.0,                       # valuation → 95 (very cheap)
        analyst_buy_pct=1.0, analyst_upside_pct=30.0,  # analyst → 100
        insider_net_buy_ratio=1.0,            # insider → 100
        seasonality_win_rate=30.0,            # headwind → 30
        seasonality_avg_return_pct=-1.0,
        seasonality_total_years=5,
    ))
    assert set(ev.present_axes) == {"valuation", "analyst", "insider", "seasonality"}
    assert ev.coverage_score == pytest.approx(1.0)
    assert ev.valuation_score == pytest.approx(95.0)
    assert ev.analyst_score == pytest.approx(100.0)
    assert ev.insider_score == pytest.approx(100.0)
    assert ev.seasonality_score == pytest.approx(30.0)
    # (95 + 100 + 100 + 0.5*30) / (1+1+1+0.5) = 310 / 3.5
    assert ev.aggregate_score == pytest.approx(310.0 / 3.5)
    assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC


def test_deferred_axes_recorded_but_excluded_from_coverage():
    ev = _build(_ctx(
        forward_pe=8.0,
        analyst_buy_pct=1.0, analyst_upside_pct=30.0,
        insider_net_buy_ratio=1.0,
        seasonality_win_rate=30.0,
        seasonality_avg_return_pct=-1.0,
        seasonality_total_years=5,
    ))
    assert ev.earnings_trend_score is None
    assert any("earnings_trend:deferred" in r for r in ev.unavailable_reasons)
    assert any("event_alpha:deferred" in r for r in ev.unavailable_reasons)
    # earnings_trend / event alpha do not count against coverage (4 scored axes)
    assert ev.coverage_score == pytest.approx(1.0)


# ── partial coverage (2 of 4) ──────────────────────────────────────────────────

def test_partial_coverage_two_of_four():
    ev = _build(_ctx(
        forward_pe=8.0,                # valuation present
        insider_net_buy_ratio=0.0,     # insider present (neutral 50)
        # no analyst, no seasonality
    ))
    assert set(ev.present_axes) == {"valuation", "insider"}
    assert ev.coverage_score == pytest.approx(0.5)
    assert ev.analyst_score is None
    assert ev.seasonality_score is None
    # aggregate over present axes only: (95 + 50) / (1 + 1)
    assert ev.aggregate_score == pytest.approx((95.0 + 50.0) / 2.0)
    assert any("analyst:" in r for r in ev.unavailable_reasons)
    assert any("seasonality:" in r for r in ev.unavailable_reasons)


# ── zero coverage → unavailable-like ──────────────────────────────────────────

def test_zero_coverage_yields_no_aggregate():
    ev = _build(_ctx())  # all enrichment None
    assert ev.present_axes == ()
    assert ev.coverage_score == pytest.approx(0.0)
    assert ev.aggregate_score is None
    assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC


# ── seasonality cap actually lowers its influence ─────────────────────────────

def test_seasonality_cap_lowers_its_influence():
    # valuation high (95), seasonality low (30). With the 0.5 cap the aggregate
    # is pulled toward valuation vs. an equal-weight mean.
    ev = _build(_ctx(
        forward_pe=8.0,
        seasonality_win_rate=30.0,
        seasonality_avg_return_pct=-1.0,
        seasonality_total_years=5,
    ))
    equal_weight = (95.0 + 30.0) / 2.0            # 62.5
    capped = (95.0 + 0.5 * 30.0) / (1.0 + 0.5)    # 73.33
    assert ev.aggregate_score == pytest.approx(capped)
    assert ev.aggregate_score > equal_weight


def test_seasonality_cap_weight_is_strictly_lower_than_other_axes():
    cfg = create_company_quality_context_evidence_builder()._config
    assert cfg.seasonality_weight < cfg.valuation_weight
    assert cfg.seasonality_weight < cfg.analyst_weight
    assert cfg.seasonality_weight < cfg.insider_weight


# ── metadata exposes per-axis sub-scores for Phase I attribution ──────────────

def test_metadata_exposes_axis_scores():
    ev = _build(_ctx(forward_pe=8.0, insider_net_buy_ratio=0.0))
    axis_scores = ev.metadata["axis_scores"]
    assert axis_scores["valuation"] == pytest.approx(95.0)
    assert axis_scores["insider"] == pytest.approx(50.0)
    assert axis_scores["analyst"] is None
    assert axis_scores["seasonality"] is None


# ── config from_mapping ───────────────────────────────────────────────────────

def test_config_from_mapping_defaults():
    cfg = CompanyQualityContextConfig.from_mapping({})
    assert cfg.evidence_status == EvidenceStatus.DIAGNOSTIC
    assert cfg.valuation_weight == pytest.approx(1.0)
    assert cfg.seasonality_weight == pytest.approx(0.5)
    assert cfg.scored_axis_count == 4


# ── shared-scorer extraction is byte-identical to the use-case methods ─────────

@pytest.mark.parametrize("ctx", [
    _ctx(forward_pe=8.0),
    _ctx(forward_pe=12.0),
    _ctx(forward_pe=18.0),
    _ctx(forward_pe=25.0),
    _ctx(forward_pe=45.0),
    _ctx(analyst_buy_pct=0.8, analyst_upside_pct=20.0),
    _ctx(insider_net_buy_ratio=0.5),
    _ctx(seasonality_win_rate=70.0, seasonality_avg_return_pct=2.0, seasonality_total_years=6),
    _ctx(seasonality_win_rate=70.0, seasonality_avg_return_pct=2.0, seasonality_total_years=3),
])
def test_shared_scorers_match_use_case_methods(ctx):
    uc = AssessSignalUseCase()
    neutral = uc._config.missing_data.neutral_score
    scoring = uc._config.scoring

    assert cqs.score_forward_pe(
        ctx,
        very_cheap_pe=scoring.forward_pe.very_cheap_pe,
        cheap_pe=scoring.forward_pe.cheap_pe,
        fair_pe=scoring.forward_pe.fair_pe,
        expensive_pe=scoring.forward_pe.expensive_pe,
        very_cheap_score=scoring.forward_pe.very_cheap_score,
        cheap_score=scoring.forward_pe.cheap_score,
        fair_score=scoring.forward_pe.fair_score,
        expensive_score=scoring.forward_pe.expensive_score,
        post_expensive_pe_step=scoring.forward_pe.post_expensive_pe_step,
        post_expensive_score_decay=scoring.forward_pe.post_expensive_score_decay,
        neutral_score=neutral,
    ) == uc._score_forward_pe(ctx)

    assert cqs.score_analyst(
        ctx,
        buy_score_max_points=scoring.analyst.buy_score_max_points,
        upside_score_max_points=scoring.analyst.upside_score_max_points,
        upside_cap_pct=scoring.analyst.upside_cap_pct,
        neutral_score=neutral,
    ) == uc._score_analyst(ctx)

    assert cqs.score_insider_activity(
        ctx, neutral_score=neutral
    ) == uc._score_insider_activity(ctx)

    assert cqs.score_seasonality(
        ctx,
        tailwind_min_avg_return_pct=scoring.seasonality.tailwind_min_avg_return_pct,
        tailwind_min_win_rate_pct=scoring.seasonality.tailwind_min_win_rate_pct,
        headwind_max_avg_return_pct=scoring.seasonality.headwind_max_avg_return_pct,
        headwind_max_win_rate_pct=scoring.seasonality.headwind_max_win_rate_pct,
        neutral_score=neutral,
    ) == uc._score_seasonality(ctx)


# ── round-trip serialization ──────────────────────────────────────────────────

def test_evidence_to_dict_from_dict_round_trip():
    ev = _build(_ctx(forward_pe=8.0, insider_net_buy_ratio=0.0))
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    restored = CompanyQualityContextEvidence.from_dict(ev.to_dict())
    assert restored.aggregate_score == pytest.approx(ev.aggregate_score)
    assert restored.present_axes == ev.present_axes
    assert restored.coverage_score == pytest.approx(ev.coverage_score)
