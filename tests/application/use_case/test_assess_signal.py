"""
Tests for AssessSignalUseCase and SignalAssessment value objects.

All tests are pure unit tests — no DB, no providers, no mocks needed.
AssessSignalUseCase has no external dependencies; it is pure computation
over a SignalContext.

Run with:
    python -m pytest tests/application/use_case/test_assess_signal.py -v
"""

from datetime import date

import pytest

from src.application.use_case.assess_signal_use_case import (
    AnalystScoringConfig,
    AssessSignalRequest,
    AssessSignalResponse,
    AssessSignalUseCase,
    ForwardPeScoringConfig,
    SeasonalityScoringConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
    SignalMissingDataConfig,
    SignalScoringConfig,
)
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    SignalAssessment,
    SignalContext,
    SignalStrength,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _ctx(**kwargs) -> SignalContext:
    """Build a SignalContext with minimal required fields."""
    return SignalContext(ticker="BBCA", snapshot_date=date.today(), **kwargs)


def _assess(**kwargs) -> AssessSignalResponse:
    """Execute use case with a SignalContext built from kwargs."""
    uc = AssessSignalUseCase()
    return uc.execute(AssessSignalRequest(ticker="BBCA", signal_context=_ctx(**kwargs)))


# ── DTOs ─────────────────────────────────────────────────────────────────────


class TestAssessSignalRequestDTO:
    def test_signal_context_defaults_to_none(self):
        req = AssessSignalRequest(ticker="BBCA")
        assert req.signal_context is None

    def test_response_property_shortcuts(self):
        uc = AssessSignalUseCase()
        resp = uc.execute(AssessSignalRequest(ticker="BBCA"))
        assert isinstance(resp.score, int)
        assert isinstance(resp.strength, str)
        assert isinstance(resp.entry_quality, str)


# ── use case scoring ──────────────────────────────────────────────────────────


class TestAssessSignalUseCaseScoring:
    def setup_method(self):
        self.uc = AssessSignalUseCase()

    def _run(self, ctx: SignalContext) -> AssessSignalResponse:
        return self.uc.execute(AssessSignalRequest(ticker="BBCA", signal_context=ctx))

    # neutral baseline

    def test_all_factors_none_returns_score_50(self):
        resp = self._run(_ctx())
        assert resp.score == 50
        assert resp.assessment.strength == SignalStrength.MODERATE
        assert resp.assessment.entry_quality == EntryQuality.WATCH

    def test_empty_request_uses_neutral_context(self):
        resp = self.uc.execute(AssessSignalRequest(ticker="BBCA"))
        assert resp.score == 50

    # full signal extremes

    def test_all_strong_factors_produces_high_score(self):
        resp = self._run(_ctx(
            bandar_broad_score=6, bandar_max_range=6,
            foreign_flow_quality=1.0,
            insider_net_buy_ratio=1.0,
            seasonality_win_rate=90.0, seasonality_avg_return_pct=3.0,
            seasonality_total_years=5, seasonality_back_years=5,
            analyst_buy_pct=1.0, analyst_upside_pct=30.0,
            forward_pe=8.0,
        ))
        # Expected: (100*.20 + 100*.20 + 100*.20 + 90*.15 + 100*.15 + 95*.10) = 98.0
        assert resp.score == 98
        assert resp.assessment.strength == SignalStrength.STRONG
        assert resp.assessment.entry_quality == EntryQuality.ENTER

    def test_all_weak_factors_produces_low_score(self):
        # Using None for seasonality/forward_pe to avoid headwind paradox
        resp = self._run(_ctx(
            bandar_broad_score=-6, bandar_max_range=6,
            foreign_flow_quality=0.0,
            insider_net_buy_ratio=-1.0,
            analyst_buy_pct=0.0, analyst_upside_pct=0.0,
        ))
        # Expected: (0*.20 + 0*.20 + 0*.20 + 50*.15 + 0*.15 + 50*.10) = 12.5
        # Python's round() uses banker's rounding: round(12.5) = 12 (rounds to even)
        assert resp.score == 12
        assert resp.assessment.strength == SignalStrength.WEAK
        assert resp.assessment.entry_quality == EntryQuality.AVOID

    # bandar normalization

    def test_bandar_max_positive_maps_to_100(self):
        resp = self._run(_ctx(bandar_broad_score=6, bandar_max_range=6))
        assert resp.assessment.breakdown_dict["bandar_intensity"] == pytest.approx(100.0)

    def test_bandar_max_negative_maps_to_0(self):
        resp = self._run(_ctx(bandar_broad_score=-6, bandar_max_range=6))
        assert resp.assessment.breakdown_dict["bandar_intensity"] == pytest.approx(0.0)

    def test_bandar_zero_maps_to_50(self):
        resp = self._run(_ctx(bandar_broad_score=0, bandar_max_range=6))
        assert resp.assessment.breakdown_dict["bandar_intensity"] == pytest.approx(50.0)

    def test_bandar_with_optional_signals_uses_extended_range(self):
        # With all 3 optional signals: max_range = (3+3)*2 = 12
        # broad_score=6, max_range=12 → (6+12)/24*100 = 75.0
        resp = self._run(_ctx(bandar_broad_score=6, bandar_max_range=12))
        assert resp.assessment.breakdown_dict["bandar_intensity"] == pytest.approx(75.0)

    # insider activity

    def test_insider_full_buy_maps_to_100(self):
        # ratio=+1.0 (full buying) → (1.0+1.0)/2*100 = 100
        resp = self._run(_ctx(insider_net_buy_ratio=1.0))
        assert resp.assessment.breakdown_dict["insider_activity"] == pytest.approx(100.0)

    def test_insider_full_sell_maps_to_0(self):
        # ratio=-1.0 (full selling) → (-1.0+1.0)/2*100 = 0
        resp = self._run(_ctx(insider_net_buy_ratio=-1.0))
        assert resp.assessment.breakdown_dict["insider_activity"] == pytest.approx(0.0)

    def test_insider_neutral_maps_to_50(self):
        # ratio=0.0 (neutral) → (0.0+1.0)/2*100 = 50
        resp = self._run(_ctx(insider_net_buy_ratio=0.0))
        assert resp.assessment.breakdown_dict["insider_activity"] == pytest.approx(50.0)

    # seasonality

    def test_seasonality_tailwind_uses_win_rate_directly(self):
        # avg_return > 0 AND win_rate > 50 → tailwind → component = win_rate
        resp = self._run(_ctx(
            seasonality_win_rate=80.0,
            seasonality_avg_return_pct=2.0,
            seasonality_total_years=5,
            seasonality_back_years=5,
        ))
        assert resp.assessment.breakdown_dict["seasonality_edge"] == pytest.approx(80.0)

    def test_seasonality_headwind_uses_low_win_rate_as_low_score(self):
        # avg_return < 0 AND win_rate < 50 → headwind → component = win_rate
        resp = self._run(_ctx(
            seasonality_win_rate=20.0,
            seasonality_avg_return_pct=-2.0,
            seasonality_total_years=5,
            seasonality_back_years=5,
        ))
        assert resp.assessment.breakdown_dict["seasonality_edge"] == pytest.approx(20.0)

    def test_seasonality_neutral_gives_50(self):
        # avg_return > 0 but win_rate ≤ 50 → neither tailwind nor headwind
        resp = self._run(_ctx(seasonality_win_rate=40.0, seasonality_avg_return_pct=0.5))
        assert resp.assessment.breakdown_dict["seasonality_edge"] == pytest.approx(50.0)

    def test_seasonality_missing_avg_return_gives_neutral(self):
        resp = self._run(_ctx(seasonality_win_rate=80.0))  # avg_return_pct=None
        assert resp.assessment.breakdown_dict["seasonality_edge"] == pytest.approx(50.0)

    # analyst

    def test_analyst_full_buy_and_max_upside_gives_100(self):
        resp = self._run(_ctx(analyst_buy_pct=1.0, analyst_upside_pct=30.0))
        assert resp.assessment.breakdown_dict["analyst_consensus"] == pytest.approx(100.0)

    def test_analyst_zero_buy_and_no_upside_gives_0(self):
        resp = self._run(_ctx(analyst_buy_pct=0.0, analyst_upside_pct=0.0))
        assert resp.assessment.breakdown_dict["analyst_consensus"] == pytest.approx(0.0)

    def test_analyst_upside_capped_at_30_pct(self):
        # Upside > 30% should be capped at 40 pts (same as exactly 30%)
        resp_30 = self._run(_ctx(analyst_buy_pct=0.0, analyst_upside_pct=30.0))
        resp_60 = self._run(_ctx(analyst_buy_pct=0.0, analyst_upside_pct=60.0))
        assert (resp_30.assessment.breakdown_dict["analyst_consensus"] ==
                pytest.approx(resp_60.assessment.breakdown_dict["analyst_consensus"]))

    def test_analyst_negative_upside_treated_as_zero(self):
        resp = self._run(_ctx(analyst_buy_pct=1.0, analyst_upside_pct=-10.0))
        # buy_score = 60.0, upside_score = max(0, min(30,-10))/30*40 = 0
        assert resp.assessment.breakdown_dict["analyst_consensus"] == pytest.approx(60.0)

    # forward P/E

    def test_forward_pe_under_10_is_95(self):
        resp = self._run(_ctx(forward_pe=8.0))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(95.0)

    def test_forward_pe_exactly_10_is_95(self):
        resp = self._run(_ctx(forward_pe=10.0))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(95.0)

    def test_forward_pe_12_5_interpolates(self):
        # pe=12.5 in band 10→15: progress=0.5, score=95-0.5*20=85.0
        resp = self._run(_ctx(forward_pe=12.5))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(85.0)

    def test_forward_pe_exactly_15_is_75(self):
        resp = self._run(_ctx(forward_pe=15.0))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(75.0)

    def test_forward_pe_expensive_above_30(self):
        # pe=35: max(0, 25 - (35-30)/10*15) = max(0, 25-7.5) = 17.5
        resp = self._run(_ctx(forward_pe=35.0))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(17.5)

    def test_forward_pe_none_gives_neutral(self):
        resp = self._run(_ctx(forward_pe=None))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(50.0)

    def test_forward_pe_zero_or_negative_gives_neutral(self):
        resp = self._run(_ctx(forward_pe=0.0))
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(50.0)

    # strength classification

    def test_insider_full_buy_plus_bandar_max_gives_score_70_strong(self):
        # bandar=100, insider=100, others neutral:
        # total = 100*.20 + 50*.20 + 100*.20 + 50*.15 + 50*.15 + 50*.10 = 70.0
        resp = self._run(_ctx(bandar_broad_score=6, bandar_max_range=6, insider_net_buy_ratio=1.0))
        assert resp.score == 70
        assert resp.assessment.strength == SignalStrength.STRONG
        assert resp.assessment.entry_quality == EntryQuality.ENTER

    def test_insider_high_plus_bandar_max_gives_moderate(self):
        # insider_net_buy_ratio=7/9 → score=(7/9+1)/2*100=88.89; bandar=100, others neutral:
        # total = 100*.20 + 50*.20 + 88.89*.20 + 50*.15 + 50*.15 + 50*.10
        # = 20 + 10 + 17.78 + 7.5 + 7.5 + 5 = 67.78 → 68
        resp = self._run(_ctx(bandar_broad_score=6, bandar_max_range=6, insider_net_buy_ratio=7/9))
        assert resp.score == 68
        assert resp.assessment.strength == SignalStrength.MODERATE

    def test_score_below_45_is_weak(self):
        # insider=-1.0→0, others neutral: total=50*.20+50*.20+0*.20+50*.15+50*.15+50*.10=40
        resp = self._run(_ctx(insider_net_buy_ratio=-1.0))
        assert resp.score == 40
        assert resp.assessment.strength == SignalStrength.WEAK
        assert resp.assessment.entry_quality == EntryQuality.AVOID

    def test_strength_and_entry_quality_are_consistent(self):
        for kwargs in [
            dict(bandar_broad_score=6, bandar_max_range=6, insider_net_buy_ratio=1.0),
            dict(),
            dict(insider_net_buy_ratio=-1.0),
        ]:
            resp = self._run(_ctx(**kwargs))
            if resp.assessment.strength == SignalStrength.STRONG:
                assert resp.assessment.entry_quality == EntryQuality.ENTER
            elif resp.assessment.strength == SignalStrength.MODERATE:
                assert resp.assessment.entry_quality == EntryQuality.WATCH
            else:
                assert resp.assessment.entry_quality == EntryQuality.AVOID

    def test_classification_thresholds_are_configurable(self):
        uc = AssessSignalUseCase(config=SignalEngineConfig(
            classification=SignalClassificationConfig(
                strong_min_score=80,
                moderate_min_score=60,
            )
        ))
        resp = uc.execute(AssessSignalRequest(
            ticker="BBCA",
            signal_context=_ctx(),
        ))

        assert resp.score == 50
        assert resp.assessment.strength == SignalStrength.WEAK
        assert resp.assessment.entry_quality == EntryQuality.AVOID

    def test_scoring_thresholds_are_configurable(self):
        uc = AssessSignalUseCase(config=SignalEngineConfig(
            missing_data=SignalMissingDataConfig(neutral_score=40.0),
            scoring=SignalScoringConfig(
                seasonality=SeasonalityScoringConfig(
                    tailwind_min_avg_return_pct=1.0,
                    tailwind_min_win_rate_pct=60.0,
                ),
                analyst=AnalystScoringConfig(
                    buy_score_max_points=50.0,
                    upside_score_max_points=50.0,
                    upside_cap_pct=50.0,
                ),
                forward_pe=ForwardPeScoringConfig(
                    very_cheap_pe=5.0,
                    cheap_pe=10.0,
                    fair_pe=15.0,
                    expensive_pe=20.0,
                    very_cheap_score=100.0,
                    cheap_score=80.0,
                    fair_score=40.0,
                    expensive_score=10.0,
                ),
            ),
        ))
        resp = uc.execute(AssessSignalRequest(
            ticker="BBCA",
            signal_context=_ctx(
                seasonality_win_rate=55.0,
                seasonality_avg_return_pct=0.5,
                analyst_buy_pct=1.0,
                analyst_upside_pct=50.0,
                forward_pe=10.0,
            ),
        ))

        assert resp.assessment.breakdown_dict["seasonality_edge"] == pytest.approx(40.0)
        assert resp.assessment.breakdown_dict["analyst_consensus"] == pytest.approx(100.0)
        assert resp.assessment.breakdown_dict["forward_valuation"] == pytest.approx(80.0)

    # breakdown structure

    def test_breakdown_contains_all_six_keys(self):
        resp = self._run(_ctx())
        assert set(resp.assessment.breakdown_dict.keys()) == {
            "bandar_intensity",
            "foreign_flow_quality",
            "insider_activity",
            "seasonality_edge",
            "analyst_consensus",
            "forward_valuation",
        }

    # determinism

    def test_score_is_deterministic(self):
        ctx = _ctx(bandar_broad_score=3, bandar_max_range=6, insider_net_buy_ratio=0.556)
        req = AssessSignalRequest(ticker="BBCA", signal_context=ctx)
        r1 = self.uc.execute(req)
        r2 = self.uc.execute(req)
        assert r1.assessment.score == r2.assessment.score
        assert r1.assessment.strength == r2.assessment.strength
        assert r1.assessment.breakdown == r2.assessment.breakdown

    # score bounds

    def test_score_is_always_in_0_to_100(self):
        extremes = [
            _ctx(bandar_broad_score=99, bandar_max_range=6),    # over-range high
            _ctx(bandar_broad_score=-99, bandar_max_range=6),   # over-range low
            _ctx(forward_pe=200.0),
            _ctx(analyst_upside_pct=500.0, analyst_buy_pct=2.0),
        ]
        for ctx in extremes:
            resp = self._run(ctx)
            assert 0 <= resp.score <= 100, f"score out of range for {ctx}"

    # rationale

    def test_rationale_contains_summary_line(self):
        resp = self._run(_ctx(insider_net_buy_ratio=1.0))
        summary = resp.assessment.rationale[-1]
        assert "score" in summary.lower()
        assert str(resp.score) in summary

    def test_rationale_notes_missing_data(self):
        resp = self._run(_ctx())  # all None
        missing_lines = [line for line in resp.assessment.rationale if "no data" in line]
        assert len(missing_lines) >= 4

    # coverage warning

    def test_coverage_warning_when_3_or_more_factors_missing(self):
        resp = self._run(_ctx(bandar_broad_score=3, bandar_max_range=6))
        assert resp.coverage_warning is not None
        assert "5/6" in resp.coverage_warning
        assert "Refresh or import enrichment data" in resp.coverage_warning

    def test_no_coverage_warning_with_sufficient_data(self):
        # 4 factors provided → only 2 missing → below the 3-factor warning threshold
        resp = self._run(_ctx(
            bandar_broad_score=3, bandar_max_range=6,
            foreign_flow_quality=0.7,
            insider_net_buy_ratio=0.556,
            seasonality_win_rate=65.0, seasonality_avg_return_pct=1.5,
        ))
        assert resp.coverage_warning is None

    def test_seasonality_with_less_than_five_years_is_not_directional(self):
        resp = self._run(_ctx(
            seasonality_win_rate=80.0,
            seasonality_avg_return_pct=3.0,
            seasonality_total_years=4,
        ))
        bd = resp.assessment.breakdown_dict
        assert bd["seasonality_edge"] == pytest.approx(50.0)
        assert "Seasonal edge: no data" in " ".join(resp.assessment.rationale)


# ── value object ──────────────────────────────────────────────────────────────


class TestSignalAssessmentValueObject:
    def _make(self, score: int = 50) -> SignalAssessment:
        return SignalAssessment(
            ticker="BBCA",
            score=score,
            strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH,
            breakdown=(("bandar_intensity", 50.0),),
            rationale=("Score 50 — MODERATE, WATCH",),
            snapshot_date=date.today(),
            signal_authority_coverage=None,
        )

    def test_frozen_raises_on_mutation(self):
        assessment = self._make()
        with pytest.raises((AttributeError, TypeError)):
            assessment.score = 99  # type: ignore

    def test_score_out_of_range_raises(self):
        with pytest.raises(ValueError, match="0–100"):
            SignalAssessment(
                ticker="BBCA",
                score=101,
                strength=SignalStrength.STRONG,
                entry_quality=EntryQuality.ENTER,
                breakdown=(),
                rationale=(),
                snapshot_date=date.today(),
                signal_authority_coverage=None,
            )

    def test_score_zero_is_valid(self):
        a = self._make(score=0)
        assert a.score == 0

    def test_score_100_is_valid(self):
        a = self._make(score=100)
        assert a.score == 100

    def test_score_label_strong(self):
        a = SignalAssessment(
            ticker="BBCA", score=75, strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.ENTER, breakdown=(), rationale=(), snapshot_date=date.today(),
            signal_authority_coverage=None,
        )
        assert "75" in a.score_label
        assert "★" in a.score_label

    def test_score_label_non_strong(self):
        a = self._make(score=50)
        assert "50" in a.score_label
        assert "·" in a.score_label

    def test_breakdown_dict_property(self):
        a = SignalAssessment(
            ticker="BBCA", score=60, strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH,
            breakdown=(("bandar_intensity", 75.0), ("insider_activity", 44.0)),
            rationale=(), snapshot_date=date.today(),
            signal_authority_coverage=None,
        )
        d = a.breakdown_dict
        assert isinstance(d, dict)
        assert d["bandar_intensity"] == pytest.approx(75.0)
        assert d["insider_activity"] == pytest.approx(44.0)

    def test_to_dict_includes_all_fields(self):
        a = self._make()
        d = a.to_dict()
        assert set(d.keys()) == {
            "ticker", "score", "legacy_conditioned_score", "strength", "entry_quality",
            "breakdown", "rationale", "snapshot_date",
            "signal_authority_coverage",
            "raw_exact_score", "alpha_trigger_score", "decision_constraints",
        }
        assert d["ticker"] == "BBCA"
        assert d["score"] == 50
        assert d["raw_exact_score"] is None
        assert d["alpha_trigger_score"] is None


class TestSignalContext:
    def test_frozen_raises_on_mutation(self):
        ctx = SignalContext(ticker="BBCA", snapshot_date=date.today())
        with pytest.raises((AttributeError, TypeError)):
            ctx.ticker = "TLKM"  # type: ignore

    def test_defaults_are_all_none_or_false(self):
        ctx = SignalContext(ticker="BBCA", snapshot_date=date.today())
        assert ctx.bandar_broad_score is None
        assert ctx.bandar_max_range == 6
        assert ctx.foreign_flow_quality is None
        assert ctx.insider_net_buy_ratio is None
        assert ctx.seasonality_win_rate is None
        assert ctx.seasonality_avg_return_pct is None
        assert ctx.analyst_buy_pct is None
        assert ctx.analyst_upside_pct is None
        assert ctx.forward_pe is None


# ── signal_authority_coverage naming (HIGH-2) ─────────────────────────────────
# confidence_score/coverage_score aliases are removed entirely — there is one
# canonical field, signal_authority_coverage, with no compatibility property.

class TestSignalAuthorityCoverageNaming:
    def _make_assessment(self, signal_authority_coverage: float = 0.75) -> SignalAssessment:
        return SignalAssessment(
            ticker="BBCA",
            score=60,
            strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH,
            breakdown=(("bandar_intensity", 60.0),),
            rationale=(),
            snapshot_date=date.today(),
            signal_authority_coverage=signal_authority_coverage,
        )

    def test_signal_assessment_has_no_removed_aliases(self):
        a = self._make_assessment(0.75)
        assert a.signal_authority_coverage == pytest.approx(0.75)
        assert not hasattr(a, "coverage_score")
        assert not hasattr(a, "confidence_score")

    def test_to_dict_emits_canonical_key_only(self):
        a = self._make_assessment(0.80)
        d = a.to_dict()
        assert "signal_authority_coverage" in d
        assert d["signal_authority_coverage"] == pytest.approx(0.80)
        assert "coverage_score" not in d
        assert "confidence_score" not in d

    def test_signal_assessment_score_and_entry_quality_unchanged_by_naming(self):
        a = self._make_assessment(0.60)
        assert a.score == 60
        assert a.entry_quality == EntryQuality.WATCH
        assert a.signal_authority_coverage == pytest.approx(0.60)


def test_archived_scorer_returns_null_authority_coverage():
    # 1. AssessSignalUseCase.execute() returns:
    # response.signal_authority_coverage is None
    # response.assessment.signal_authority_coverage is None
    from src.application.dto.assess_signal import AssessSignalRequest
    from src.application.use_case.assess_signal_use_case import AssessSignalUseCase

    use_case = AssessSignalUseCase()
    req = AssessSignalRequest(ticker="BBCA")
    response = use_case.execute(req)

    assert response.signal_authority_coverage is None
    assert response.assessment.signal_authority_coverage is None


def test_archived_assessment_serialization_includes_null():
    # 2. Archived assessment serialization includes:
    # assessment.to_dict()["signal_authority_coverage"] is None
    from src.application.dto.assess_signal import AssessSignalRequest
    from src.application.use_case.assess_signal_use_case import AssessSignalUseCase

    use_case = AssessSignalUseCase()
    req = AssessSignalRequest(ticker="BBCA")
    response = use_case.execute(req)

    d = response.assessment.to_dict()
    assert "signal_authority_coverage" in d
    assert d["signal_authority_coverage"] is None


def test_signal_assessment_nullable_validity():
    # 3. SignalAssessment(signal_authority_coverage=None, ...) is valid.
    # 4. Numeric values 0.0 and 1.0 are valid.
    # 5. Values below 0.0 and above 1.0 raise ValueError.
    a_none = SignalAssessment(
        ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
        snapshot_date=date.today(), signal_authority_coverage=None
    )
    assert a_none.signal_authority_coverage is None

    a_0 = SignalAssessment(
        ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
        snapshot_date=date.today(), signal_authority_coverage=0.0
    )
    assert a_0.signal_authority_coverage == 0.0

    a_1 = SignalAssessment(
        ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
        snapshot_date=date.today(), signal_authority_coverage=1.0
    )
    assert a_1.signal_authority_coverage == 1.0

    with pytest.raises(ValueError, match="signal_authority_coverage must be 0.0–1.0"):
        SignalAssessment(
            ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
            snapshot_date=date.today(), signal_authority_coverage=-0.1
        )

    with pytest.raises(ValueError, match="signal_authority_coverage must be 0.0–1.0"):
        SignalAssessment(
            ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
            snapshot_date=date.today(), signal_authority_coverage=1.1
        )


def test_omitting_signal_authority_coverage_raises_type_error():
    # 6. Omitting signal_authority_coverage from direct construction raises TypeError.
    # This locks removal of the fabricated default.
    with pytest.raises(TypeError):
        # We deliberately omit signal_authority_coverage
        SignalAssessment(
            ticker="BBCA", score=50, strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH, breakdown=(), rationale=(),
            snapshot_date=date.today(),
        )


def test_archived_scorer_behavior_preservation():
    # Capture score, strength, entry quality, breakdown, and rationale for a representative context.
    # Assert those values are unchanged.
    # Assert only canonical authority coverage is now None.
    from src.application.dto.assess_signal import AssessSignalRequest
    from src.application.use_case.assess_signal_use_case import AssessSignalUseCase

    use_case = AssessSignalUseCase()

    # Representative context (e.g. empty/defaults)
    req = AssessSignalRequest(ticker="BBCA")
    response = use_case.execute(req)

    assert response.assessment.score == 50
    assert response.assessment.strength == SignalStrength.MODERATE
    assert response.assessment.entry_quality == EntryQuality.WATCH
    # Verify breakdown values are neutral 50
    breakdown_dict = response.assessment.breakdown_dict
    assert breakdown_dict["bandar_intensity"] == 50.0
    assert breakdown_dict["foreign_flow_quality"] == 50.0
    assert breakdown_dict["insider_activity"] == 50.0
    assert breakdown_dict["seasonality_edge"] == 50.0
    assert breakdown_dict["analyst_consensus"] == 50.0
    assert breakdown_dict["forward_valuation"] == 50.0

    # Rationale contains the expected lines
    assert response.assessment.rationale[-1].startswith("Archived baseline score ")
    assert not any(line.startswith("Signal score") for line in response.assessment.rationale)

    # Assert missing-data warning contains: archived baseline score defaulted to neutral
    assert response.coverage_warning is not None
    assert "archived baseline score defaulted to neutral" in response.coverage_warning

    # Assert ONLY signal_authority_coverage is None
    assert response.assessment.signal_authority_coverage is None
