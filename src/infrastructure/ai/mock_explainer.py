"""
Mock explainer adapter for testing and offline use.

Implements AIExplainer port with static responses (no API calls).

Layer: Infrastructure
"""

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment

# Template for mock explanations by risk level
MOCK_EXPLANATIONS = {
    "HIGH_RISK": """The analysis indicates elevated risk conditions for {ticker}. \
The RSI reading of {rsi} suggests the stock may be in overbought territory, \
meaning recent price increases could be unsustainable. Additionally, the \
relationship between short-term (EMA) and long-term (SMA) moving averages \
shows signs of weakening momentum.

Both technical indicators align on this assessment, resulting in high \
confidence (100/100). This doesn't mean the stock will definitely decline, \
but rather that caution is warranted based on current technical conditions.

DISCLAIMER: This is analysis only, not trading advice.""",
    "MODERATE": """The technical indicators for {ticker} show mixed signals. \
The RSI at {rsi} is in the neutral zone, indicating neither extreme buying \
nor selling pressure. The moving averages (SMA and EMA) are relatively close, \
suggesting the market is consolidating without a strong directional trend.

The moderate risk assessment with {confidence}% confidence reflects the \
ambiguity in the current technical picture. The indicators don't strongly \
agree on direction, which is typical during market transitions.

DISCLAIMER: This is analysis only, not trading advice.""",
    "LOW_RISK": """The analysis shows favorable technical conditions for {ticker}. \
The RSI at {rsi} indicates healthy buying interest without being excessive. \
The EMA (short-term average) is positioned favorably relative to the SMA \
(long-term average), suggesting positive momentum.

Both indicators support this low-risk assessment with high confidence, \
meaning the technical signals are aligned. However, low technical risk \
doesn't guarantee price appreciation - it simply means current conditions \
appear stable.

DISCLAIMER: This is analysis only, not trading advice.""",
}


class MockExplainer:
    """Mock explainer for testing and offline fallback.

    Returns templated explanations without making API calls.
    Useful for:
    - Unit testing
    - Development without API keys
    - Offline operation
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    def explain_assessment(
        self,
        ticker: str,
        assessment: RiskAssessment,
        snapshot: IndicatorSnapshot,
    ) -> str:
        """Generate mock explanation based on risk level.

        Args:
            ticker: Stock ticker symbol
            assessment: The risk assessment result
            snapshot: The indicator snapshot

        Returns:
            Templated explanation string
        """
        template = MOCK_EXPLANATIONS.get(
            assessment.risk_level_name,
            MOCK_EXPLANATIONS["MODERATE"],
        )

        return template.format(
            ticker=ticker,
            rsi=f"{snapshot.rsi:.2f}",
            confidence=assessment.confidence,
        )
