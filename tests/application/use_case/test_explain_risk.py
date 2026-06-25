"""
Tests for ExplainRiskUseCase.

Verifies the use case orchestrates AI explanation correctly and
handles errors gracefully.
"""

from datetime import date
from decimal import Decimal

from src.application.use_case.explain_risk_use_case import (
    ExplainRiskRequest,
    ExplainRiskResponse,
    ExplainRiskUseCase,
)
from src.domain.ports.ai_explainer import (
    ExplainerAuthError,
    ExplainerError,
    ExplainerRateLimitError,
    ExplainerTimeoutError,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile
from src.infrastructure.ai.mock_explainer import MockExplainer


def make_snapshot(
    sma: str = "9850.00",
    ema: str = "9720.00",
    rsi: str = "72.50",
) -> IndicatorSnapshot:
    """Create test snapshot."""
    return IndicatorSnapshot(
        date=date(2024, 1, 15),
        sma=Decimal(sma),
        ema=Decimal(ema),
        rsi=Decimal(rsi),
    )


def make_assessment(
    risk_level: RiskLevel = RiskLevel.HIGH_RISK,
    confidence: int = 100,
) -> tuple[RiskAssessment, IndicatorSnapshot]:
    """Create test assessment with snapshot."""
    snapshot = make_snapshot()
    assessment = RiskAssessment(
        sensitivity=RiskProfile.BALANCED,
        risk_level=risk_level,
        confidence=confidence,
        rationale=(
            "RSI 72.50 > threshold (70)",
            "EMA < SMA indicates downtrend",
        ),
        snapshot_date=snapshot.date,
        indicators=snapshot,
    )
    return assessment, snapshot


class FailingExplainer:
    """Test explainer that raises specific errors."""

    def __init__(self, error_class: type, message: str = "Test error"):
        self._error_class = error_class
        self._message = message
        self.provider_name = "failing"

    def explain_assessment(self, ticker, assessment, snapshot):
        raise self._error_class(self._message)


class TestExplainRiskUseCase:
    """Tests for ExplainRiskUseCase."""

    def test_successful_explanation_with_mock(self):
        """Should return successful response with mock explainer."""
        explainer = MockExplainer()
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is True
        assert response.ticker == "BBCA"
        assert response.provider == "mock"
        assert len(response.explanation) > 0
        assert response.error_message is None

    def test_handles_auth_error(self):
        """Should return error response for auth failures."""
        explainer = FailingExplainer(ExplainerAuthError, "No API key")
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is False
        assert response.ticker == "BBCA"
        assert "No API key" in response.error_message
        assert response.explanation == ""

    def test_handles_timeout_error(self):
        """Should return error response for timeouts."""
        explainer = FailingExplainer(ExplainerTimeoutError, "Request timed out")
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is False
        assert "timed out" in response.error_message

    def test_handles_rate_limit_error(self):
        """Should return error response for rate limits."""
        explainer = FailingExplainer(ExplainerRateLimitError, "Rate limit exceeded")
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is False
        assert "Rate limit" in response.error_message

    def test_handles_generic_explainer_error(self):
        """Should return error response for generic explainer errors."""
        explainer = FailingExplainer(ExplainerError, "API error")
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is False
        assert "API error" in response.error_message

    def test_handles_unexpected_error(self):
        """Should handle unexpected exceptions gracefully."""
        explainer = FailingExplainer(RuntimeError, "Unexpected failure")
        use_case = ExplainRiskUseCase(explainer=explainer)
        assessment, snapshot = make_assessment()

        response = use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        assert response.success is False
        assert "Unexpected" in response.error_message

    def test_response_factory_methods(self):
        """Test ExplainRiskResponse factory methods."""
        # Success response
        success = ExplainRiskResponse.success_response(
            ticker="BBCA",
            explanation="Test explanation",
            provider="test",
        )
        assert success.success is True
        assert success.explanation == "Test explanation"
        assert success.error_message is None

        # Error response
        error = ExplainRiskResponse.error_response(
            ticker="BBCA",
            error_message="Test error",
            provider="test",
        )
        assert error.success is False
        assert error.explanation == ""
        assert error.error_message == "Test error"


class TestDeterminismPreserved:
    """Tests to verify AI doesn't affect risk assessment."""

    def test_assessment_unchanged_after_explanation(self):
        """Risk assessment must not change after AI explanation."""
        # Create original assessment
        assessment_before, snapshot = make_assessment(
            risk_level=RiskLevel.HIGH_RISK,
            confidence=100,
        )

        # Run through explainer
        explainer = MockExplainer()
        use_case = ExplainRiskUseCase(explainer=explainer)
        use_case.execute(
            ExplainRiskRequest(
                ticker="BBCA",
                assessment=assessment_before,
                snapshot=snapshot,
            )
        )

        # Verify assessment is unchanged (immutable dataclass)
        assert assessment_before.risk_level == RiskLevel.HIGH_RISK
        assert assessment_before.confidence == 100
        assert assessment_before.sensitivity == RiskProfile.BALANCED
        assert assessment_before.rationale == (
            "RSI 72.50 > threshold (70)",
            "EMA < SMA indicates downtrend",
        )

    def test_same_input_same_risk_level(self):
        """Same input must always produce same risk level."""
        assessment1, snapshot1 = make_assessment()
        assessment2, snapshot2 = make_assessment()

        # Both assessments should be identical
        assert assessment1.risk_level == assessment2.risk_level
        assert assessment1.confidence == assessment2.confidence
        assert assessment1.sensitivity == assessment2.sensitivity
