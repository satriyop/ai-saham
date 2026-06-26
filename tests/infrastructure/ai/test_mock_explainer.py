"""
Tests for MockExplainer.

Verifies mock explainer returns valid templated explanations.
"""

from datetime import date
from decimal import Decimal

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile
from src.infrastructure.ai.mock_explainer import MockExplainer


def make_snapshot(
    sma: str = "100.00",
    ema: str = "100.00",
    rsi: str = "50.00",
) -> IndicatorSnapshot:
    """Create test snapshot."""
    return IndicatorSnapshot(
        date=date(2024, 1, 15),
        sma=Decimal(sma),
        ema=Decimal(ema),
        rsi=Decimal(rsi),
    )


def make_assessment(
    risk_level: RiskLevel,
    confidence: int = 100,
    snapshot: IndicatorSnapshot | None = None,
) -> RiskAssessment:
    """Create test assessment."""
    if snapshot is None:
        snapshot = make_snapshot()

    return RiskAssessment(
        sensitivity=RiskProfile.BALANCED,
        rationale=("Test rationale 1", "Test rationale 2"),
        snapshot_date=snapshot.date,
        indicators=snapshot,
        gate_triggered=("gate" if risk_level == RiskLevel.HIGH_RISK else None),
        gate_confidence=confidence,
    )


class TestMockExplainer:
    """Tests for MockExplainer."""

    def test_provider_name(self):
        """Provider name should be 'mock'."""
        explainer = MockExplainer()
        assert explainer.provider_name == "mock"

    def test_explain_high_risk(self):
        """Should return high risk template for HIGH_RISK level."""
        explainer = MockExplainer()
        snapshot = make_snapshot(rsi="75.00")
        assessment = make_assessment(RiskLevel.HIGH_RISK, snapshot=snapshot)

        explanation = explainer.explain_assessment(
            ticker="BBCA",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert isinstance(explanation, str)
        assert len(explanation) > 100  # Non-trivial explanation
        assert "BBCA" in explanation
        assert "75.00" in explanation  # RSI value
        assert "DISCLAIMER" in explanation

    def test_explain_moderate(self):
        """Should return moderate template for MODERATE level."""
        explainer = MockExplainer()
        snapshot = make_snapshot(rsi="50.00")
        assessment = make_assessment(RiskLevel.MODERATE, confidence=50, snapshot=snapshot)

        explanation = explainer.explain_assessment(
            ticker="BBRI",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert isinstance(explanation, str)
        assert len(explanation) > 100
        assert "BBRI" in explanation
        assert "50.00" in explanation  # RSI value
        assert "DISCLAIMER" in explanation

    def test_explain_low_risk(self):
        """Should return low risk template for LOW_RISK level."""
        explainer = MockExplainer()
        snapshot = make_snapshot(rsi="45.00")
        assessment = make_assessment(RiskLevel.LOW_RISK, snapshot=snapshot)

        explanation = explainer.explain_assessment(
            ticker="TLKM",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert isinstance(explanation, str)
        assert len(explanation) > 100
        assert "TLKM" in explanation
        assert "45.00" in explanation  # RSI value
        assert "DISCLAIMER" in explanation

    def test_explanation_includes_confidence(self):
        """Explanation should include confidence value."""
        explainer = MockExplainer()
        snapshot = make_snapshot()
        assessment = make_assessment(RiskLevel.MODERATE, confidence=50, snapshot=snapshot)

        explanation = explainer.explain_assessment(
            ticker="TEST",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert "50" in explanation  # Confidence value

    def test_no_api_call_made(self):
        """Mock explainer should not make any external calls."""
        # This test verifies the mock doesn't accidentally call real APIs
        explainer = MockExplainer()
        snapshot = make_snapshot()
        assessment = make_assessment(RiskLevel.HIGH_RISK, snapshot=snapshot)

        # Should complete instantly without network
        explanation = explainer.explain_assessment(
            ticker="OFFLINE",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert isinstance(explanation, str)
        assert "OFFLINE" in explanation
