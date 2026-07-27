from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.swing_analysis import (
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
    SwingAnalysisWorkflowResponse,
    SwingVerdict,
)
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def _assess_response() -> AssessSignalResponse:
    assessment = SignalAssessment(
        identity=SWING_TRADE_SETUP_IDENTITY,
        ticker="BBCA",
        snapshot_date=date(2026, 6, 18),
        score=75.0,
        strength=SignalStrength.STRONG,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("bandar_intensity", 80.0),),
        rationale=("supportive",),
        signal_authority_coverage=None,
    )
    return AssessSignalResponse(
        ticker="BBCA",
        assessment=assessment,
        coverage_warning=None,
    )


def _trade_setup() -> TradeSetup:
    return TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 18),
        action=SetupAction.ENTER,
        signal_score=75,
        signal_score_raw=75,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )


def test_availability_valid_states():
    avail1 = SignalAssessmentAvailability(status=SignalAssessmentStatus.AVAILABLE)
    assert avail1.status == SignalAssessmentStatus.AVAILABLE
    assert avail1.unavailable_reason is None

    avail2 = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    assert avail2.status == SignalAssessmentStatus.UNAVAILABLE
    assert (
        avail2.unavailable_reason == SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE
    )


def test_availability_available_with_reason_raises_value_error():
    with pytest.raises(ValueError, match="AVAILABLE requires no unavailable reason"):
        SignalAssessmentAvailability(
            status=SignalAssessmentStatus.AVAILABLE,
            unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
        )


def test_availability_unavailable_without_reason_raises_value_error():
    with pytest.raises(ValueError, match="UNAVAILABLE requires a reason"):
        SignalAssessmentAvailability(status=SignalAssessmentStatus.UNAVAILABLE)


def test_availability_status_string_raises_type_error():
    with pytest.raises(TypeError, match="status must be a SignalAssessmentStatus"):
        SignalAssessmentAvailability(status="AVAILABLE")


def test_availability_reason_string_raises_type_error():
    with pytest.raises(
        TypeError, match="unavailable_reason must be a SignalAssessmentUnavailableReason"
    ):
        SignalAssessmentAvailability(
            status=SignalAssessmentStatus.UNAVAILABLE,
            unavailable_reason="no_production_signal_evidence",
        )


def test_verdict_validation_types():
    with pytest.raises(
        TypeError, match="signal_assessment_availability must be a SignalAssessmentAvailability"
    ):
        SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability="AVAILABLE",
        )


def test_verdict_available_no_signal_raises_value_error():
    avail = SignalAssessmentAvailability(status=SignalAssessmentStatus.AVAILABLE)
    with pytest.raises(ValueError, match="AVAILABLE requires signal_assessment to be present"):
        SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=avail,
        )


def test_verdict_unavailable_with_signal_raises_value_error():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    with pytest.raises(ValueError, match="UNAVAILABLE requires signal_assessment to be None"):
        SwingVerdict(
            trade_setup=None,
            signal_assessment=_assess_response(),
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=avail,
        )


def test_verdict_unavailable_with_trade_setup_raises_value_error():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    with pytest.raises(ValueError, match="UNAVAILABLE requires trade_setup to be None"):
        SwingVerdict(
            trade_setup=_trade_setup(),
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=avail,
        )


def test_verdict_unavailable_with_signal_preview_raises_value_error():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    with pytest.raises(
        ValueError, match="UNAVAILABLE requires market_context_signal_preview to be None"
    ):
        SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            market_context_signal_preview=_assess_response(),
            signal_assessment_availability=avail,
        )


def test_verdict_unavailable_with_trade_setup_preview_raises_value_error():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    with pytest.raises(
        ValueError, match="UNAVAILABLE requires market_context_trade_setup_preview to be None"
    ):
        SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            market_context_trade_setup_preview=_trade_setup(),
            signal_assessment_availability=avail,
        )


def test_response_validation_types():
    with pytest.raises(
        TypeError, match="signal_assessment_availability must be a SignalAssessmentAvailability"
    ):
        SwingAnalysisWorkflowResponse(
            ticker="BBCA",
            today=date(2026, 6, 18),
            refresh_actions=(),
            data_freshness=None,
            flow_detail=None,
            broker_detail=None,
            candles=[],
            latest_close=Decimal("100"),
            accumulation_candidate=None,
            risk_response=None,
            atr_value=None,
            sizing=None,
            setup_eval=None,
            setup_sizing=None,
            broker_quality_note=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            market_regime=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            signal_assessment_availability="AVAILABLE",
        )


def test_response_available_no_signal_raises_value_error():
    avail = SignalAssessmentAvailability(status=SignalAssessmentStatus.AVAILABLE)
    with pytest.raises(ValueError, match="AVAILABLE requires signal_assessment to be present"):
        SwingAnalysisWorkflowResponse(
            ticker="BBCA",
            today=date(2026, 6, 18),
            refresh_actions=(),
            data_freshness=None,
            flow_detail=None,
            broker_detail=None,
            candles=[],
            latest_close=Decimal("100"),
            accumulation_candidate=None,
            risk_response=None,
            atr_value=None,
            sizing=None,
            setup_eval=None,
            setup_sizing=None,
            broker_quality_note=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            market_regime=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            signal_assessment_availability=avail,
            signal_assessment=None,
        )


def test_response_unavailable_with_signal_raises_value_error():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )
    with pytest.raises(ValueError, match="UNAVAILABLE requires signal_assessment to be None"):
        SwingAnalysisWorkflowResponse(
            ticker="BBCA",
            today=date(2026, 6, 18),
            refresh_actions=(),
            data_freshness=None,
            flow_detail=None,
            broker_detail=None,
            candles=[],
            latest_close=Decimal("100"),
            accumulation_candidate=None,
            risk_response=None,
            atr_value=None,
            sizing=None,
            setup_eval=None,
            setup_sizing=None,
            broker_quality_note=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            market_regime=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            signal_assessment_availability=avail,
            signal_assessment=_assess_response(),
        )


def test_response_verdict_availability_mismatch_raises_value_error():
    avail_available = SignalAssessmentAvailability(status=SignalAssessmentStatus.AVAILABLE)
    avail_unavailable = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
    )

    verdict = SwingVerdict(
        trade_setup=None,
        signal_assessment=_assess_response(),
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=avail_available,
    )

    with pytest.raises(ValueError, match="Response availability must match verdict availability"):
        SwingAnalysisWorkflowResponse(
            ticker="BBCA",
            today=date(2026, 6, 18),
            refresh_actions=(),
            data_freshness=None,
            flow_detail=None,
            broker_detail=None,
            candles=[],
            latest_close=Decimal("100"),
            accumulation_candidate=None,
            risk_response=None,
            atr_value=None,
            sizing=None,
            setup_eval=None,
            setup_sizing=None,
            broker_quality_note=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            market_regime=None,
            take_profit_pct=Decimal("5"),
            stop_loss_pct=Decimal("5"),
            regime_label=None,
            signal_assessment_availability=avail_unavailable,
            signal_assessment=None,
            verdict=verdict,
        )


def test_verdict_serialization_available():
    avail = SignalAssessmentAvailability(status=SignalAssessmentStatus.AVAILABLE)
    verdict = SwingVerdict(
        trade_setup=None,
        signal_assessment=_assess_response(),
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=avail,
    )
    payload = verdict.to_dict()
    assert payload["signal_assessment_status"] == "AVAILABLE"
    assert payload["signal_assessment_unavailable_reason"] is None


@pytest.mark.parametrize(
    "reason",
    [
        SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
        SignalAssessmentUnavailableReason.SIGNAL_ENGINE_UNAVAILABLE,
        SignalAssessmentUnavailableReason.ASSESSMENT_FAILED,
    ],
)
def test_verdict_serialization_unavailable(reason):
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=reason,
    )
    verdict = SwingVerdict(
        trade_setup=None,
        signal_assessment=None,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=avail,
    )
    payload = verdict.to_dict()
    assert payload["signal_assessment_status"] == "UNAVAILABLE"
    assert payload["signal_assessment_unavailable_reason"] == reason.value
    assert payload["signal_assessment"] is None
    assert payload["trade_setup"] is None


def test_response_to_dict_verdict_keys():
    avail = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.ASSESSMENT_FAILED,
    )
    verdict = SwingVerdict(
        trade_setup=None,
        signal_assessment=None,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=avail,
    )
    resp = SwingAnalysisWorkflowResponse(
        ticker="BBCA",
        today=date(2026, 6, 18),
        refresh_actions=(),
        data_freshness=None,
        flow_detail=None,
        broker_detail=None,
        candles=[],
        latest_close=Decimal("100"),
        accumulation_candidate=None,
        risk_response=None,
        atr_value=None,
        sizing=None,
        setup_eval=None,
        setup_sizing=None,
        broker_quality_note=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        market_regime=None,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        regime_label=None,
        signal_assessment_availability=avail,
        signal_assessment=None,
        verdict=verdict,
    )
    payload = resp.to_dict()
    verdict_payload = payload["verdict"]
    assert verdict_payload["signal_assessment_status"] == "UNAVAILABLE"
    assert verdict_payload["signal_assessment_unavailable_reason"] == "assessment_failed"
    assert verdict_payload["signal_assessment"] is None
    assert verdict_payload["trade_setup"] is None
