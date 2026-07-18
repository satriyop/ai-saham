"""Regression tests for SwingAnalysisResponseAssembler invariants.

Layer: Application (test)
"""
import pytest

from src.application.dto.swing_analysis import (
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
    SwingVerdict,
)
from src.application.services.swing_analysis_response_assembler import (
    SwingAnalysisResponseAssembler,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from tests.application.use_case.swing_analysis_workflow_fixtures import _request


def test_assemble_rejects_state_and_verdict_availability_mismatch():
    state_availability = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=SignalAssessmentUnavailableReason.ASSESSMENT_FAILED,
    )

    verdict_availability = SignalAssessmentAvailability(
        status=SignalAssessmentStatus.UNAVAILABLE,
        unavailable_reason=(
            SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE
        ),
    )

    state = SwingAnalysisWorkflowState(
        signal_assessment_availability=state_availability,
        verdict=SwingVerdict(
            trade_setup=None,
            signal_assessment=None,
            risk_response=None,
            market_regime=None,
            signal_assessment_availability=verdict_availability,
        ),
    )

    with pytest.raises(
        ValueError,
        match="state and verdict signal assessment availability differ",
    ):
        SwingAnalysisResponseAssembler().assemble(_request(), state)
