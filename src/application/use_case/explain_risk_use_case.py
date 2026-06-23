"""
ExplainRisk use case - generate AI explanations for risk assessments.

Orchestrates AI explanation generation for pre-computed risk assessments.
The AI is read-only: it explains results but does NOT generate or influence them.

Layer: Application
Depends on: AIExplainer port, RiskAssessment value object
"""

from dataclasses import dataclass

from src.domain.ports.ai_explainer import (
    AIExplainer,
    ExplainerAuthError,
    ExplainerError,
    ExplainerRateLimitError,
    ExplainerTimeoutError,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


@dataclass
class ExplainRiskRequest:
    """Request DTO for risk explanation."""

    ticker: str
    assessment: RiskAssessment
    snapshot: IndicatorSnapshot


@dataclass
class ExplainRiskResponse:
    """Response DTO containing AI explanation."""

    ticker: str
    explanation: str
    provider: str
    success: bool
    error_message: str | None = None

    @classmethod
    def success_response(
        cls,
        ticker: str,
        explanation: str,
        provider: str,
    ) -> "ExplainRiskResponse":
        """Create a successful response."""
        return cls(
            ticker=ticker,
            explanation=explanation,
            provider=provider,
            success=True,
            error_message=None,
        )

    @classmethod
    def error_response(
        cls,
        ticker: str,
        error_message: str,
        provider: str,
    ) -> "ExplainRiskResponse":
        """Create an error response."""
        return cls(
            ticker=ticker,
            explanation="",
            provider=provider,
            success=False,
            error_message=error_message,
        )


class ExplainRiskUseCase:
    """
    Use case for generating AI explanations of risk assessments.

    This use case:
        1. Takes a pre-computed RiskAssessment
        2. Passes it to an AIExplainer adapter
        3. Returns the generated explanation

    Important:
        - The AI does NOT compute or modify risk levels
        - AI is optional enhancement - system works without it
        - Errors are caught and returned gracefully (no exceptions)

    Usage:
        explainer = ExplainerFactory.create(provider="claude")
        use_case = ExplainRiskUseCase(explainer)
        response = use_case.execute(request)

        if response.success:
            print(response.explanation)
        else:
            print(f"Warning: {response.error_message}")
    """

    def __init__(self, explainer: AIExplainer) -> None:
        """
        Initialize with AI explainer dependency.

        Args:
            explainer: AIExplainer adapter for generating explanations
        """
        self._explainer = explainer

    def execute(self, request: ExplainRiskRequest) -> ExplainRiskResponse:
        """
        Generate AI explanation for a risk assessment.

        This method catches all errors and returns them as error responses
        rather than raising exceptions. This allows the CLI to continue
        even when AI explanation fails.

        Args:
            request: Contains ticker, assessment, and snapshot

        Returns:
            ExplainRiskResponse with explanation or error message
        """
        provider = self._get_provider_name()

        try:
            explanation = self._explainer.explain_assessment(
                ticker=request.ticker,
                assessment=request.assessment,
                snapshot=request.snapshot,
            )

            return ExplainRiskResponse.success_response(
                ticker=request.ticker,
                explanation=explanation,
                provider=provider,
            )

        except ExplainerAuthError as e:
            return ExplainRiskResponse.error_response(
                ticker=request.ticker,
                error_message=str(e),
                provider=provider,
            )

        except ExplainerTimeoutError:
            return ExplainRiskResponse.error_response(
                ticker=request.ticker,
                error_message="AI explanation timed out",
                provider=provider,
            )

        except ExplainerRateLimitError as e:
            return ExplainRiskResponse.error_response(
                ticker=request.ticker,
                error_message=str(e),
                provider=provider,
            )

        except ExplainerError as e:
            return ExplainRiskResponse.error_response(
                ticker=request.ticker,
                error_message=str(e),
                provider=provider,
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return ExplainRiskResponse.error_response(
                ticker=request.ticker,
                error_message=f"Unexpected error: {e}",
                provider=provider,
            )

    def _get_provider_name(self) -> str:
        """Get provider name from explainer."""
        if hasattr(self._explainer, "provider_name"):
            return self._explainer.provider_name
        return "unknown"
