from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.swing_analysis import SwingEvidence
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.swing_analysis_serialization import signal_response_to_dict
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState


def test_swing_evidence_to_dict_includes_flow_confirmation_evidence():
    candidate = SimpleNamespace(
        ticker="BBCA",
        foreign_flow_evidence=SimpleNamespace(
            component_breakdown=(
                ("cons", 40.0), ("streak", 19.0), ("vwap", 20.0),
                ("rsi", 10.0), ("flow", 10.0), ("bb", 0.0), ("inst", 15.0),
            ),
            confirmation_status="CONFIRMED",
            flow_direction="POSITIVE",
        ),
        bandar_detector=None,
        bci_label="CLUSTER",
        bci_tier1_count=3,
        latest_candle_date=date(2026, 6, 25),
    )
    flow_ev = FlowConfirmationEvidenceBuilder().build(candidate, analysis_date=date(2026, 6, 25))
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
        flow_confirmation_evidence=flow_ev,
    )

    d = evidence.to_dict()

    assert "flow_confirmation_evidence" in d
    fc = d["flow_confirmation_evidence"]
    assert fc is not None
    assert fc["ticker"] == "BBCA"
    assert fc["confirmation_status"] == "CONFIRMED"
    assert fc["flow_direction"] == "POSITIVE"
    assert isinstance(fc["flow_signals"], list)
    assert all(s["key"] not in ("bb", "rsi") for s in fc["flow_signals"])


def test_swing_evidence_to_dict_flow_confirmation_none_when_not_built():
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
    )

    d = evidence.to_dict()

    assert "flow_confirmation_evidence" in d
    assert d["flow_confirmation_evidence"] is None


def test_swing_evidence_to_dict_includes_setup_phase():
    phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=1.0,
        conviction_score=0.8,
        sequence_valid=True,
        reasons=("breakout: VWAP reclaim",),
    )
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
        setup_phase=phase,
    )

    d = evidence.to_dict()

    assert d["setup_phase"]["current_phase"] == "BREAKOUT_CONFIRMATION"
    assert d["setup_phase"]["sequence_valid"] is True


def test_signal_response_to_dict_emits_coverage_fields():
    from datetime import date as _date

    from src.application.use_case.assess_signal_use_case import AssessSignalResponse
    from src.domain.value_objects.signal_assessment import (
        EntryQuality,
        SignalAssessment,
        SignalStrength,
    )

    assessment = SignalAssessment(
        ticker="BBCA",
        snapshot_date=_date(2026, 7, 8),
        score=72,
        strength=SignalStrength.STRONG,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("setup_quality_group", 80.0),),
        rationale=(),
        confidence_score=0.85,
    )
    response = AssessSignalResponse(
        ticker="BBCA",
        assessment=assessment,
        evidence_confidence=0.85,
    )

    d = signal_response_to_dict(response)
    assert d is not None
    assert "coverage_score" in d
    assert d["coverage_score"] == pytest.approx(0.85)
    assert "evidence_confidence" in d
    assert "confidence_score" in d
    assert d["evidence_confidence"] == d["coverage_score"]
    assert d["confidence_score"] == d["coverage_score"]


def test_signal_response_to_dict_none_returns_none():
    assert signal_response_to_dict(None) is None
