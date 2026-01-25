"""
AIExplainer port interface.

Defines the contract for AI-generated explanations of risk assessments.
AI is read-only - it explains results but does NOT generate or influence them.

Layer: Domain (Port)
"""

from typing import Protocol

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment


class AIExplainer(Protocol):
    """Port for AI-generated explanations of analysis results.

    AI is read-only - it explains results but does not influence them.
    The risk assessment has already been computed by the deterministic
    rule engine before this is called.

    Implementations:
        - ClaudeExplainer: Anthropic Claude API
        - OpenAIExplainer: OpenAI GPT API
        - GeminiExplainer: Google Gemini API
        - OllamaExplainer: Local Ollama server
        - MockExplainer: Testing/offline fallback
    """

    def explain_assessment(
        self,
        ticker: str,
        assessment: RiskAssessment,
        snapshot: IndicatorSnapshot,
    ) -> str:
        """Generate human-readable explanation for a risk assessment.

        Args:
            ticker: Stock ticker symbol (e.g., "BBCA")
            assessment: The deterministic risk assessment result
            snapshot: The indicator values that were evaluated

        Returns:
            Natural language explanation for non-technical users.
            Should be 2-3 paragraphs explaining what the indicators mean
            and why the risk level was assigned.

        Raises:
            ExplainerError: If explanation generation fails
        """
        ...


class ExplainerError(Exception):
    """Base exception for AI explainer errors."""

    pass


class ExplainerTimeoutError(ExplainerError):
    """Raised when LLM request times out."""

    pass


class ExplainerAuthError(ExplainerError):
    """Raised when API key is invalid or missing."""

    pass


class ExplainerRateLimitError(ExplainerError):
    """Raised when rate limit is exceeded (local or remote)."""

    pass
