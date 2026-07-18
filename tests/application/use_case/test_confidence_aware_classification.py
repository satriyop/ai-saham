"""
SignalEngine classification tests (HIGH-2).

_classify_entry gates on directional strength only: STRONG -> ENTER,
MODERATE -> WATCH, WEAK -> AVOID. Evidence authority coverage is applied
exactly once downstream, by DecisionPolicyService, not by classification.
These tests use a bare SignalEngineConfig()/DecisionPolicyConfig(), whose
RISK_ON min_signal_authority_coverage dataclass default is 0.70 (HIGH-2
Finding 1: matches the production YAML default, not the old, unenforced
dataclass default of 0.0) — so single-group evidence below that floor is
correctly capped to WATCH here despite a raw STRONG directional score. See
test_decision_policy.py / test_signal_decision_constraints.py for more
authority-coverage-floor scenarios.
"""

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
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import EntryQuality, SignalStrength
from tests.application.use_case.signal_evidence_fixtures import (
    _wrap_flow_evidence,
    _wrap_setup_evidence,
)
from src.domain.value_objects.canonical_signal_evidence_input import CanonicalSignalEvidenceInput

SNAP = date(2026, 7, 3)


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


def _setup(match: str) -> SetupEvidence:
    strength = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}[match]
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match=match,
        match_strength=strength,
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


def _flow(capped_strength: float) -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="flow",
        score=40.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
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


def _execute(**kwargs):
    setup_evidence = kwargs.pop("setup_evidence", None)
    flow_confirmation_evidence = kwargs.pop("flow_confirmation_evidence", None)
    if setup_evidence is not None or flow_confirmation_evidence is not None:
        kwargs["canonical_evidence"] = CanonicalSignalEvidenceInput(
            setup=_wrap_setup_evidence(setup_evidence),
            flow=_wrap_flow_evidence(flow_confirmation_evidence),
        )
    req = AssessSignalEvidenceRequest(ticker="TEST", snapshot_date=SNAP, **kwargs)
    return AssessSignalEvidenceUseCase().execute(req)


def test_full_evidence_strong_score_can_enter():
    resp = _execute(
        setup_evidence=_setup("MATCH"),
        flow_confirmation_evidence=_flow(0.90),
    )

    assert resp.assessment.score == 96
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.signal_authority_coverage == pytest.approx(1.0)
    assert resp.assessment.entry_quality == EntryQuality.ENTER


def test_high_score_with_setup_only_authority_coverage_capped_to_watch():
    # HIGH-2 Finding 1: raw classification (STRONG score) is coverage-blind,
    # but DecisionPolicyService's default 0.70 RISK_ON floor caps this
    # single-group 0.60 coverage to WATCH, not ENTER.
    resp = _execute(setup_evidence=_setup("MATCH"))

    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.signal_authority_coverage == pytest.approx(0.60)
    assert resp.assessment.entry_quality == EntryQuality.WATCH


def test_high_score_with_flow_only_authority_coverage_capped_to_watch():
    # HIGH-2 Finding 1: single-group flow-only 0.40 coverage is below the
    # default 0.70 RISK_ON floor, so DecisionPolicyService caps the raw
    # STRONG/ENTER classification to WATCH.
    resp = _execute(flow_confirmation_evidence=_flow(0.90))

    assert resp.assessment.score == 90
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.signal_authority_coverage == pytest.approx(0.40)
    assert resp.assessment.entry_quality == EntryQuality.WATCH


def test_no_evidence_moderate_score_raises_no_production_signal_evidence_error():
    from src.application.exceptions import NoProductionSignalEvidenceError
    with pytest.raises(NoProductionSignalEvidenceError):
        _execute()
