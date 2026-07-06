"""
Unit tests for AssessSignalEvidenceUseCase — Phase 4 staged evidence-first aggregator.

Tests cover:
  - Both groups missing → neutral prior + zero confidence
  - Only flow evidence → renormalized to flow score alone
  - Only setup evidence → renormalized to setup score alone
  - Both groups present → weighted combination
  - Each flag individually (VALUATION_STRETCHED, ANALYST_BEARISH, INSIDER_SELLING)
  - Flags below threshold don't fire
  - Multiple flags stack
  - Score clamped to 0–100
  - Custom group weights via config
  - Coverage warning thresholds
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceRequest,
    AssessSignalEvidenceUseCase,
)
from src.application.use_case.assess_signal_use_case import (
    AnalystBearishFlagConfig,
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    InsiderSellingFlagConfig,
    DecisionPolicyConfig,
    RegimeDecisionPolicyConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
    SignalFlagsConfig,
    ValuationStretchedFlagConfig,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.signal_assessment import SignalContext, SignalStrength

SNAP = date(2026, 7, 3)


# ── helpers ───────────────────────────────────────────────────────────────────

def _use_case(config: SignalEngineConfig | None = None) -> AssessSignalEvidenceUseCase:
    return AssessSignalEvidenceUseCase(config=config)


def _req(**kwargs) -> AssessSignalEvidenceRequest:
    defaults = {"ticker": "TEST", "snapshot_date": SNAP}
    defaults.update(kwargs)
    return AssessSignalEvidenceRequest(**defaults)


def _setup_evidence(match: str = "MATCH") -> SetupEvidence:
    strengths = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match=match,
        match_strength=strengths[match],
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        rs_vs_ihsg_5d=1.05,
        rs_freshness=Freshness.FRESH,
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow_evidence(capped_strength: float = 0.70) -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="cons", score=40.0, weight=40.0,
        direction=Direction.BULLISH, freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=capped_strength,
        capped_strength=capped_strength,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def _ctx(**kwargs) -> SignalContext:
    return SignalContext(ticker="TEST", snapshot_date=SNAP, **kwargs)


def _setup_phase(*, coverage: float, conviction: float) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=conviction,
        coverage_score=coverage,
        conviction_score=conviction,
        sequence_valid=True,
    )


# ── no evidence tests ─────────────────────────────────────────────────────────

def test_both_groups_missing_returns_neutral_prior():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.assessment.score == 50
    assert resp.evidence_confidence == 0.0
    assert resp.raw_group_score == 50


def test_both_groups_missing_strength_is_moderate():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.assessment.strength == SignalStrength.MODERATE


def test_both_groups_missing_coverage_warning_present():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.coverage_warning is not None
    assert "No evidence groups present" in resp.coverage_warning


def test_both_groups_missing_no_flags_score_stays_50():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.active_flags == ()
    assert resp.flag_adjustment == 0
    assert resp.assessment.score == 50


def test_setup_phase_coverage_and_conviction_drive_decision_floors():
    config = SignalEngineConfig(
        decision_policy=DecisionPolicyConfig(
            regime_policy={
                "RISK_ON": RegimeDecisionPolicyConfig(
                    enter_allowed=True,
                    max_decision="ENTER",
                    enter_threshold=70,
                    watch_threshold=45,
                    min_coverage=0.7,
                    min_conviction=0.7,
                ),
                "NEUTRAL": RegimeDecisionPolicyConfig(),
                "RISK_OFF": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
                "VOLATILE": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
            }
        )
    )
    resp = _use_case(config).execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_setup_phase(coverage=0.2, conviction=0.2),
        )
    )

    assert resp.evidence_confidence == 1.0
    assert resp.assessment.entry_quality.value == "WATCH"
    assert any(
        "ENTER requires coverage" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


# ── single group tests ────────────────────────────────────────────────────────

def test_only_flow_evidence_renormalized_to_flow_score():
    # capped_strength=0.80 → flow group score = 80.0
    # Only flow (weight=0.40) present → renormalized score = 80.0
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.80)))
    assert resp.assessment.score == 80
    assert resp.assessment.entry_quality.name == "WATCH"
    # confidence = 0.40 / (0.60+0.40) = 0.40
    assert resp.evidence_confidence == pytest.approx(0.40)
    assert resp.assessment.confidence_score == pytest.approx(0.40)


def test_only_setup_evidence_renormalized_to_setup_score():
    # MATCH → match_strength=100.0; only setup (weight=0.60) present → score=100
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.assessment.score == 100
    assert resp.assessment.entry_quality.name == "WATCH"
    # confidence = 0.60 / 1.0 = 0.60
    assert resp.evidence_confidence == pytest.approx(0.60)
    assert resp.assessment.confidence_score == pytest.approx(0.60)


def test_partial_setup_match_gives_lower_score():
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("PARTIAL")))
    assert resp.assessment.score == 60   # match_strength=60.0


def test_no_match_setup_gives_low_score():
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("NO_MATCH")))
    assert resp.assessment.score == 20   # match_strength=20.0


# ── both groups present ───────────────────────────────────────────────────────

def test_both_groups_present_weighted_combination():
    # setup=MATCH (100.0, weight=0.60) + flow=0.50 capped (50.0, weight=0.40)
    # base_score = (100*0.60 + 50*0.40) / (0.60+0.40) = (60+20)/1.0 = 80.0
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
    ))
    assert resp.assessment.score == 80
    assert resp.evidence_confidence == pytest.approx(1.0)
    assert resp.coverage_warning is None


def test_both_groups_present_full_strength_scores_100():
    # setup=MATCH (100) + flow capped=1.0 (100) → score=100
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=1.0),
    ))
    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.entry_quality.name == "ENTER"
    assert resp.assessment.confidence_score == pytest.approx(1.0)


# ── flag tests ────────────────────────────────────────────────────────────────

def test_valuation_stretched_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(forward_pe=55.0)   # > 50.0 threshold
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert resp.flag_adjustment == -10
    assert resp.assessment.score == 40   # 50 - 10


def test_valuation_stretched_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(forward_pe=50.0)   # == threshold → NOT triggered (strictly >)
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" not in resp.active_flags


def test_valuation_stretched_not_triggered_below_threshold():
    uc = _use_case()
    ctx = _ctx(forward_pe=30.0)
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" not in resp.active_flags


def test_analyst_bearish_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(analyst_buy_pct=0.10)   # < 0.20 threshold
    resp = uc.execute(_req(signal_context=ctx))
    assert "ANALYST_BEARISH" in resp.active_flags
    assert resp.flag_adjustment == -8
    assert resp.assessment.score == 42   # 50 - 8


def test_analyst_bearish_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(analyst_buy_pct=0.20)   # == threshold → NOT triggered (strictly <)
    resp = uc.execute(_req(signal_context=ctx))
    assert "ANALYST_BEARISH" not in resp.active_flags


def test_insider_selling_flag_applies_penalty():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=-0.50)   # < -0.30 threshold
    resp = uc.execute(_req(signal_context=ctx))
    assert "INSIDER_SELLING" in resp.active_flags
    assert resp.flag_adjustment == -12
    assert resp.assessment.score == 38   # 50 - 12


def test_insider_selling_not_triggered_at_threshold():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=-0.30)   # == threshold → NOT triggered (strictly <)
    resp = uc.execute(_req(signal_context=ctx))
    assert "INSIDER_SELLING" not in resp.active_flags


def test_neutral_insider_does_not_trigger_flag():
    uc = _use_case()
    ctx = _ctx(insider_net_buy_ratio=0.0)
    resp = uc.execute(_req(signal_context=ctx))
    assert "INSIDER_SELLING" not in resp.active_flags


# ── multiple flags stack ──────────────────────────────────────────────────────

def test_multiple_flags_stack():
    uc = _use_case()
    ctx = _ctx(
        forward_pe=60.0,           # VALUATION_STRETCHED → -10
        analyst_buy_pct=0.05,      # ANALYST_BEARISH → -8
        insider_net_buy_ratio=-0.60,  # INSIDER_SELLING → -12
    )
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert "ANALYST_BEARISH" in resp.active_flags
    assert "INSIDER_SELLING" in resp.active_flags
    assert resp.flag_adjustment == -30
    # 50 - 30 = 20 → WEAK
    assert resp.assessment.score == 20
    assert resp.assessment.strength == SignalStrength.WEAK


def test_score_clamped_at_zero_with_multiple_flags():
    # Even with full evidence at score=100, if all 3 flags fire → 100-30=70, not below 0.
    # But with no evidence (score=50) and all flags: 50-30=20 (not below 0).
    # To test clamping: use NO_MATCH setup (score=20) + all 3 flags → 20-30=-10 → clamped to 0.
    uc = _use_case()
    ctx = _ctx(
        forward_pe=60.0,
        analyst_buy_pct=0.05,
        insider_net_buy_ratio=-0.60,
    )
    resp = uc.execute(_req(setup_evidence=_setup_evidence("NO_MATCH"), signal_context=ctx))
    assert resp.assessment.score == 0
    assert resp.assessment.score >= 0


# ── custom config ─────────────────────────────────────────────────────────────

def test_custom_group_weights_affect_score():
    # Custom: setup=0.80, flow=0.20
    cfg = SignalEngineConfig(
        evidence_groups=EvidenceGroupsConfig(
            setup_quality=EvidenceGroupConfig(weight=0.80),
            flow_confirmation=EvidenceGroupConfig(weight=0.20),
        )
    )
    uc = _use_case(cfg)
    # setup=PARTIAL (60), flow=capped=1.0 (100)
    # score = (60*0.80 + 100*0.20) / 1.0 = (48+20) = 68
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("PARTIAL"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=1.0),
    ))
    assert resp.assessment.score == 68


def test_custom_enter_confidence_threshold_allows_setup_only_enter():
    cfg = SignalEngineConfig(
        classification=SignalClassificationConfig(
            strong_min_score=70,
            moderate_min_score=45,
            enter_min_confidence=0.60,
            watch_min_confidence=0.40,
        )
    )
    uc = _use_case(cfg)
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.assessment.score == 100
    assert resp.assessment.confidence_score == pytest.approx(0.60)
    assert resp.assessment.entry_quality.name == "ENTER"


def test_custom_flag_threshold_changes_trigger_point():
    cfg = SignalEngineConfig(
        flags=SignalFlagsConfig(
            valuation_stretched=ValuationStretchedFlagConfig(
                enabled=True,
                forward_pe_threshold=30.0,   # tighter threshold
                score_penalty=5,
            ),
            analyst_bearish=AnalystBearishFlagConfig(),
            insider_selling=InsiderSellingFlagConfig(),
        )
    )
    uc = _use_case(cfg)
    ctx = _ctx(forward_pe=35.0)   # > 30.0 → fires with custom config
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" in resp.active_flags
    assert resp.flag_adjustment == -5


def test_disabled_flag_does_not_apply():
    cfg = SignalEngineConfig(
        flags=SignalFlagsConfig(
            valuation_stretched=ValuationStretchedFlagConfig(enabled=False),
            analyst_bearish=AnalystBearishFlagConfig(),
            insider_selling=InsiderSellingFlagConfig(),
        )
    )
    uc = _use_case(cfg)
    ctx = _ctx(forward_pe=999.0)   # way above threshold but flag disabled
    resp = uc.execute(_req(signal_context=ctx))
    assert "VALUATION_STRETCHED" not in resp.active_flags


# ── coverage warning ──────────────────────────────────────────────────────────

def test_low_confidence_emits_coverage_warning():
    # Only flow evidence (confidence=0.40 < 0.50) → warning
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    assert resp.coverage_warning is not None
    assert "40%" in resp.coverage_warning


def test_full_confidence_no_coverage_warning():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(),
    ))
    assert resp.coverage_warning is None


def test_setup_only_confidence_above_50_no_warning():
    # Only setup (confidence=0.60 >= 0.50) → no warning
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.coverage_warning is None


# ── breakdown and response shape ──────────────────────────────────────────────

def test_breakdown_includes_present_groups_and_confidence():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.70),
    ))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" in bd
    assert "flow_confirmation_group" in bd
    assert "evidence_confidence" in bd
    assert bd["setup_quality_group"] == 100.0
    assert bd["flow_confirmation_group"] == pytest.approx(70.0)
    assert bd["evidence_confidence"] == pytest.approx(100.0)


def test_breakdown_omits_missing_groups():
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" not in bd
    assert "flow_confirmation_group" in bd


def test_flag_adjustment_in_breakdown_when_nonzero():
    uc = _use_case()
    ctx = _ctx(forward_pe=55.0)
    resp = uc.execute(_req(signal_context=ctx))
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" in bd
    assert bd["flag_adjustment"] == -10.0


def test_no_flag_adjustment_in_breakdown_when_zero():
    uc = _use_case()
    resp = uc.execute(_req())
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" not in bd


def test_response_has_all_phase4_fields():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.evidence_confidence is not None
    assert isinstance(resp.active_flags, tuple)
    assert isinstance(resp.flag_adjustment, int)
    assert resp.raw_group_score is not None
