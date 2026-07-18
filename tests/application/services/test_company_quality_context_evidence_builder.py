"""Unit tests for CompanyQualityContextEvidenceBuilder and shared scorers.

Covers:
  - all four axes present
  - partial coverage (2 of 4)
  - zero coverage → aggregate None / present_axes empty
  - seasonality cap actually lowers its influence in the aggregate
  - coverage_score correctness
  - shared scorers (company_quality_scoring) match known hand-computed vectors
    against SignalScoringConfig() defaults
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
from src.application.services.signal_scoring_config import SignalScoringConfig
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.signal_assessment import SignalContext
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)

_NEUTRAL_SCORE = 50.0

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


# ── shared scorers match known hand-computed vectors ───────────────────────────
# Fixed expectations against SignalScoringConfig() defaults (very_cheap_pe=10,
# cheap_pe=15, fair_pe=20, expensive_pe=30, very_cheap_score=95, cheap_score=75,
# fair_score=50, expensive_score=25, post_expensive_pe_step=10,
# post_expensive_score_decay=15; buy_score_max_points=60,
# upside_score_max_points=40, upside_cap_pct=30). Independent of any use case —
# proves company_quality_scoring's formulas directly, not merely that two call
# sites agree.

_SCORING = SignalScoringConfig()


@pytest.mark.parametrize(
    "pe,expected_score,expected_present",
    [
        (8.0, 95.0, True),     # <= very_cheap_pe: flat very_cheap_score
        (12.0, 87.0, True),    # interpolate(12, 10, 15, 95, 75)
        (18.0, 60.0, True),    # interpolate(18, 15, 20, 75, 50)
        (25.0, 37.5, True),    # interpolate(25, 20, 30, 50, 25)
        (45.0, 2.5, True),     # post-expensive decay: 25 - (45-30)/10*15
        (None, _NEUTRAL_SCORE, False),
    ],
)
def test_score_forward_pe_known_vectors(pe, expected_score, expected_present):
    score, present = cqs.score_forward_pe(
        _ctx(forward_pe=pe),
        very_cheap_pe=_SCORING.forward_pe.very_cheap_pe,
        cheap_pe=_SCORING.forward_pe.cheap_pe,
        fair_pe=_SCORING.forward_pe.fair_pe,
        expensive_pe=_SCORING.forward_pe.expensive_pe,
        very_cheap_score=_SCORING.forward_pe.very_cheap_score,
        cheap_score=_SCORING.forward_pe.cheap_score,
        fair_score=_SCORING.forward_pe.fair_score,
        expensive_score=_SCORING.forward_pe.expensive_score,
        post_expensive_pe_step=_SCORING.forward_pe.post_expensive_pe_step,
        post_expensive_score_decay=_SCORING.forward_pe.post_expensive_score_decay,
        neutral_score=_NEUTRAL_SCORE,
    )
    assert score == pytest.approx(expected_score)
    assert present is expected_present


def test_score_analyst_known_vector():
    score, present = cqs.score_analyst(
        _ctx(analyst_buy_pct=0.8, analyst_upside_pct=20.0),
        buy_score_max_points=_SCORING.analyst.buy_score_max_points,
        upside_score_max_points=_SCORING.analyst.upside_score_max_points,
        upside_cap_pct=_SCORING.analyst.upside_cap_pct,
        neutral_score=_NEUTRAL_SCORE,
    )
    # buy_score = 0.8 * 60 = 48.0; upside_score = min(30, 20)/30 * 40 = 26.6667
    assert score == pytest.approx(48.0 + 20.0 / 30.0 * 40.0)
    assert present is True


def test_score_analyst_missing_is_neutral():
    score, present = cqs.score_analyst(
        _ctx(),
        buy_score_max_points=_SCORING.analyst.buy_score_max_points,
        upside_score_max_points=_SCORING.analyst.upside_score_max_points,
        upside_cap_pct=_SCORING.analyst.upside_cap_pct,
        neutral_score=_NEUTRAL_SCORE,
    )
    assert score == _NEUTRAL_SCORE
    assert present is False


def test_score_insider_activity_known_vector():
    score, present = cqs.score_insider_activity(
        _ctx(insider_net_buy_ratio=0.5), neutral_score=_NEUTRAL_SCORE
    )
    assert score == pytest.approx(75.0)
    assert present is True


def test_score_insider_activity_missing_is_neutral():
    score, present = cqs.score_insider_activity(_ctx(), neutral_score=_NEUTRAL_SCORE)
    assert score == _NEUTRAL_SCORE
    assert present is False


@pytest.mark.parametrize(
    "win_rate,avg_return,total_years,expected_score,expected_present",
    [
        (70.0, 2.0, 6, 70.0, True),    # tailwind: avg>0 and win>50 -> score=win
        (70.0, 2.0, 3, _NEUTRAL_SCORE, False),  # < 5 years -> neutral, absent
        (None, None, None, _NEUTRAL_SCORE, False),
    ],
)
def test_score_seasonality_known_vectors(
    win_rate, avg_return, total_years, expected_score, expected_present
):
    score, present = cqs.score_seasonality(
        _ctx(
            seasonality_win_rate=win_rate,
            seasonality_avg_return_pct=avg_return,
            seasonality_total_years=total_years,
        ),
        tailwind_min_avg_return_pct=_SCORING.seasonality.tailwind_min_avg_return_pct,
        tailwind_min_win_rate_pct=_SCORING.seasonality.tailwind_min_win_rate_pct,
        headwind_max_avg_return_pct=_SCORING.seasonality.headwind_max_avg_return_pct,
        headwind_max_win_rate_pct=_SCORING.seasonality.headwind_max_win_rate_pct,
        neutral_score=_NEUTRAL_SCORE,
    )
    assert score == pytest.approx(expected_score)
    assert present is expected_present


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
