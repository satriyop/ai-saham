from __future__ import annotations

from datetime import date

import pytest

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.canonical_signal_evidence_input import CanonicalSignalEvidenceInput
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
)
from tests.application.use_case.signal_evidence_fixtures import (
    _wrap_flow_evidence,
    _wrap_setup_evidence,
)

SNAP = date(2026, 7, 5)


def _req(**kwargs) -> AssessSignalEvidenceRequest:
    setup_evidence = kwargs.pop("setup_evidence", None)
    flow_confirmation_evidence = kwargs.pop("flow_confirmation_evidence", None)
    if setup_evidence is not None or flow_confirmation_evidence is not None:
        kwargs["canonical_evidence"] = CanonicalSignalEvidenceInput(
            setup=_wrap_setup_evidence(setup_evidence),
            flow=_wrap_flow_evidence(flow_confirmation_evidence),
        )
    return AssessSignalEvidenceRequest(
        identity=SWING_TRADE_SETUP_IDENTITY,
        **kwargs,
    )


def _excess_return(window_sessions: int, excess_return_pct: float) -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=window_sessions,
        ticker_return_pct=excess_return_pct,
        benchmark_return_pct=0.0,
        excess_return_pct=excess_return_pct,
        window_start=date(2026, 6, 1),
        window_end=SNAP,
        common_session_count=window_sessions + 1,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


def _mctx(regime: str) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.70,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=SNAP,
    )


def _setup() -> SetupEvidence:
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        benchmark_excess_return_5_session=_excess_return(5, 1.05),
        benchmark_excess_return_20_session=_excess_return(20, 1.05),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow() -> FlowConfirmationEvidence:
    sig = FlowSubSignal(
        key="cons",
        score=80.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(sig,),
        flow_score_ex_bb=80.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.80,
        capped_strength=0.80,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def test_risk_off_enter_allowed_false_caps_enter_without_mutating_score():
    response = AssessSignalEvidenceUseCase().execute(
        _req(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
            market_context=_mctx("RISK_OFF"),
            setup_family="foreign-bounce",
        )
    )

    # ADR-067: the score is the flow group score alone (was the 100/0.60 +
    # 80/0.40 blend = 92). The constraint assertions below are what this test
    # is about and none of them moved.
    assert response.assessment.score == 80
    assert response.assessment.entry_quality == EntryQuality.WATCH

    constraints = response.assessment.decision_constraints
    assert constraints is not None
    assert constraints.max_decision == "WATCH"
    assert constraints.regime == "RISK_OFF"
    assert constraints.regime_enter_allowed is False
    assert constraints.regime_size_multiplier == 0.25
    assert constraints.setup_family == "foreign_bounce"
    assert constraints.effective_size_multiplier == 0.25
    assert "RISK_OFF disables ENTER" in constraints.constraint_reasons


def test_decision_policy_receives_signal_authority_coverage_from_scorer():
    """HIGH-2: DecisionPolicyService receives signal_authority_coverage
    computed by SignalEvidenceGroupScorer from evidence presence/authority —
    it is no longer substituted from SetupPhaseSnapshot.coverage_score/
    conviction_score. This test verifies the wiring by checking that a
    single present evidence group (authority coverage 0.60) produces a
    signal_authority_coverage constraint reason under RISK_OFF's
    code-default min_signal_authority_coverage=0.80 floor.
    """
    from src.application.use_case.assess_signal_evidence_use_case import (
        AssessSignalEvidenceUseCase,
    )

    # Only setup evidence present → signal_authority_coverage = 0.60 < 0.80
    response = AssessSignalEvidenceUseCase().execute(
        _req(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            market_context=_mctx("RISK_OFF"),
            setup_family="foreign-bounce",
        )
    )

    constraints = response.assessment.decision_constraints
    assert constraints is not None
    assert any("signal_authority_coverage" in r.lower() for r in constraints.constraint_reasons), (
        f"Expected signal_authority_coverage constraint reason, got: "
        f"{constraints.constraint_reasons}"
    )

    # canonical field exists on SignalAssessment
    assert response.assessment.signal_authority_coverage is not None


def test_response_and_assessment_signal_authority_coverage_agree():
    """HIGH-2: AssessSignalResponse.signal_authority_coverage and
    SignalAssessment.signal_authority_coverage are populated from the same
    computed value — there is no separate alias/property relationship."""
    response = AssessSignalEvidenceUseCase().execute(
        _req(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
        )
    )
    assert response.signal_authority_coverage == response.assessment.signal_authority_coverage
    assert response.signal_authority_coverage is not None


def _setup_with_excess_return(excess_return_pct: float) -> SetupEvidence:
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        benchmark_excess_return_5_session=_excess_return(5, excess_return_pct),
        benchmark_excess_return_20_session=_excess_return(20, excess_return_pct),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def test_poor_benchmark_excess_return_cannot_cap_enter():
    """Task HIGH-1: a deliberately poor benchmark excess return must not cap
    an otherwise identical ENTER result — the diagnostic evidence carries no
    decision authority."""
    strong_response = AssessSignalEvidenceUseCase().execute(
        _req(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup_with_excess_return(1.05),
            flow_confirmation_evidence=_flow(),
            setup_family="foreign-bounce",
        )
    )
    assert strong_response.assessment.entry_quality == EntryQuality.ENTER

    poor_response = AssessSignalEvidenceUseCase().execute(
        _req(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup_with_excess_return(-50.0),
            flow_confirmation_evidence=_flow(),
            setup_family="foreign-bounce",
        )
    )

    assert poor_response.assessment.entry_quality == EntryQuality.ENTER
    assert poor_response.assessment.score == strong_response.assessment.score
    constraints = poor_response.assessment.decision_constraints
    if constraints is not None:
        assert not any(
            "rs_policy" in r or "benchmark_excess_return" in r.lower()
            for r in constraints.constraint_reasons
        )


def test_support_reclaim_exception_no_longer_exists():
    """Task HIGH-1 removed the broken support-reclaim exception entirely —
    the config dataclass and its production authority module must be gone,
    not merely disabled."""
    import importlib

    from src.application.services import setup_phase_config

    assert not hasattr(setup_phase_config, "SetupPhaseRSPolicyConfig")
    assert not hasattr(setup_phase_config.SetupPhaseConfig(), "rs_policy_by_setup_family")
    assert not hasattr(setup_phase_config.SetupPhaseConfig(), "rs_policy_for")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.application.services.setup_phase_rs_policy")
