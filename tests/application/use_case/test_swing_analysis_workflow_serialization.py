from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.swing_analysis import SwingEvidence
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.swing_analysis_serialization import signal_response_to_dict
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState


def test_swing_evidence_to_dict_includes_flow_confirmation_evidence():
    candidate = SimpleNamespace(
        ticker="BBCA",
        foreign_flow_evidence=ForeignFlowEvidence(
            max_score=100.0,
            score_family="composite_foreign_flow",
            flow_direction="POSITIVE",
            confirmation_status="CONFIRMED",
            net_buy_days=5,
            total_days=7,
            streak=4,
            avg_flow_ratio=8.0,
            components=(
                ForeignFlowComponentScore("cons", 33.3, 33.3, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore(
                    "streak", 25.0, 25.0, ForeignFlowComponentStatus.AVAILABLE
                ),
                ForeignFlowComponentScore("vwap", 16.7, 16.7, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("rsi", 8.3, 8.3, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("flow", 8.3, 8.3, ForeignFlowComponentStatus.AVAILABLE),
                ForeignFlowComponentScore("bb", None, 8.3, ForeignFlowComponentStatus.DISABLED),
                ForeignFlowComponentScore("inst", 12.5, 12.5, ForeignFlowComponentStatus.AVAILABLE),
            ),
        ),
        bandar_detector=None,
        bci_label="CLUSTER",
        bci_tier1_count=3,
        latest_candle_date=date(2026, 6, 25),
    )
    flow_ev = (
        FlowConfirmationEvidenceBuilder()
        .build(
            candidate,
            analysis_date=date(2026, 6, 25),
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
        )
        .evidence
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
        phase_detection_strength=0.8,
        phase_input_coverage=1.0,
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


def test_signal_response_to_dict_emits_signal_authority_coverage():
    from datetime import date as _date

    from src.application.dto.assess_signal import AssessSignalResponse
    from src.domain.value_objects.signal_assessment import (
        SWING_TRADE_SETUP_IDENTITY,
        EntryQuality,
        SignalAssessment,
        SignalStrength,
    )

    assessment = SignalAssessment(
        identity=SWING_TRADE_SETUP_IDENTITY,
        ticker="BBCA",
        snapshot_date=_date(2026, 7, 8),
        score=72,
        strength=SignalStrength.STRONG,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("setup_quality_group", 80.0),),
        rationale=(),
        signal_authority_coverage=0.85,
    )
    response = AssessSignalResponse(
        ticker="BBCA",
        assessment=assessment,
        signal_authority_coverage=0.85,
    )

    d = signal_response_to_dict(response)
    assert d is not None
    assert d["identity"] == {
        "purpose": "SWING_TRADE_SETUP",
        "policy_contract": "swing_trade_setup.v1",
    }
    assert "signal_authority_coverage" in d
    assert d["signal_authority_coverage"] == pytest.approx(0.85)
    assert "setup_readiness" in d
    assert d["setup_readiness"] is None
    # HIGH-2: removed aliases must not reappear in canonical output
    assert "coverage_score" not in d
    assert "evidence_confidence" not in d
    assert "confidence_score" not in d


def test_signal_response_to_dict_none_returns_none():
    assert signal_response_to_dict(None) is None
