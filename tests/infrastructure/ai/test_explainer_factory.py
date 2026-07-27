"""
Tests for ExplainerFactory and RateLimitedExplainer.

Verifies factory creates correct explainer types and rate limiting works.
"""

import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.domain.ports.ai_explainer import ExplainerAuthError, ExplainerRateLimitError
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.infrastructure.ai.factory import (
    SUPPORTED_PROVIDERS,
    ExplainerFactory,
    RateLimitedExplainer,
)
from src.infrastructure.ai.mock_explainer import MockExplainer


def make_snapshot() -> IndicatorSnapshot:
    """Create test snapshot."""
    return IndicatorSnapshot(
        date=date(2024, 1, 15),
        sma=Decimal("100.00"),
        ema=Decimal("100.00"),
        rsi=Decimal("50.00"),
    )


def make_assessment(snapshot: IndicatorSnapshot) -> RiskAssessment:
    """Create test assessment."""
    return RiskAssessment(
        rationale=("Test",),
        snapshot_date=snapshot.date,
        indicators=snapshot,
        gate_triggered=None,
        gate_confidence=50,
    )


class TestExplainerFactory:
    """Tests for ExplainerFactory."""

    def test_create_mock_explainer(self):
        """Should create mock explainer for 'mock' provider."""
        explainer = ExplainerFactory.create(provider="mock", with_rate_limit=False)
        assert isinstance(explainer, MockExplainer)

    def test_create_mock_explainer_case_insensitive(self):
        """Provider name should be case insensitive."""
        explainer = ExplainerFactory.create(provider="MOCK", with_rate_limit=False)
        assert isinstance(explainer, MockExplainer)

    def test_unsupported_provider_raises_error(self):
        """Should raise ValueError for unsupported provider."""
        with pytest.raises(ValueError) as exc_info:
            ExplainerFactory.create(provider="unknown")

        assert "Unsupported provider" in str(exc_info.value)
        assert "unknown" in str(exc_info.value)

    @patch.dict(os.environ, {"AI_PROVIDER": "mock"}, clear=False)
    def test_reads_provider_from_env(self):
        """Should use AI_PROVIDER env var when provider not specified."""
        explainer = ExplainerFactory.create(with_rate_limit=False)
        assert isinstance(explainer, MockExplainer)

    def test_claude_requires_api_key(self):
        """Should raise ExplainerAuthError for claude without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear all env vars to ensure no API key
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ExplainerAuthError):
                ExplainerFactory.create(provider="claude", with_rate_limit=False)

    def test_openai_requires_api_key(self):
        """Should raise ExplainerAuthError for openai without API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            with pytest.raises(ExplainerAuthError):
                ExplainerFactory.create(provider="openai", with_rate_limit=False)

    def test_gemini_requires_api_key(self):
        """Should raise ExplainerAuthError for gemini without API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            with pytest.raises(ExplainerAuthError):
                ExplainerFactory.create(provider="gemini", with_rate_limit=False)

    def test_wraps_with_rate_limiter_by_default(self):
        """Should wrap explainer with rate limiter by default."""
        explainer = ExplainerFactory.create(provider="mock")
        assert isinstance(explainer, RateLimitedExplainer)

    def test_rate_limiter_disabled_when_requested(self):
        """Should not wrap with rate limiter when disabled."""
        explainer = ExplainerFactory.create(provider="mock", with_rate_limit=False)
        assert isinstance(explainer, MockExplainer)

    def test_supported_providers_list(self):
        """All supported providers should be defined."""
        assert "claude" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "gemini" in SUPPORTED_PROVIDERS
        assert "ollama" in SUPPORTED_PROVIDERS
        assert "mock" in SUPPORTED_PROVIDERS


class TestRateLimitedExplainer:
    """Tests for RateLimitedExplainer."""

    def test_passes_through_calls(self):
        """Should pass calls through to underlying explainer."""
        mock = MockExplainer()
        limited = RateLimitedExplainer(mock, max_per_minute=10)

        snapshot = make_snapshot()
        assessment = make_assessment(snapshot)

        explanation = limited.explain_assessment(
            ticker="BBCA",
            assessment=assessment,
            snapshot=snapshot,
        )

        assert len(explanation) > 0
        assert "BBCA" in explanation

    def test_provider_name_from_wrapped(self):
        """Should return provider name from wrapped explainer."""
        mock = MockExplainer()
        limited = RateLimitedExplainer(mock, max_per_minute=10)
        assert limited.provider_name == "mock"

    def test_rate_limit_enforced(self):
        """Should enforce rate limit."""
        mock = MockExplainer()
        limited = RateLimitedExplainer(mock, max_per_minute=2)

        snapshot = make_snapshot()
        assessment = make_assessment(snapshot)

        # First two calls should succeed
        limited.explain_assessment("T1", assessment, snapshot)
        limited.explain_assessment("T2", assessment, snapshot)

        # Third call should fail
        with pytest.raises(ExplainerRateLimitError) as exc_info:
            limited.explain_assessment("T3", assessment, snapshot)

        assert "rate limit" in str(exc_info.value).lower()

    def test_unlimited_when_zero(self):
        """Should allow unlimited calls when max_per_minute is 0."""
        mock = MockExplainer()
        limited = RateLimitedExplainer(mock, max_per_minute=0)

        snapshot = make_snapshot()
        assessment = make_assessment(snapshot)

        # Should allow many calls without rate limit error
        for i in range(10):
            explanation = limited.explain_assessment(f"T{i}", assessment, snapshot)
            assert len(explanation) > 0

    def test_rate_limit_resets_after_window(self):
        """Rate limit should reset after the time window passes."""
        mock = MockExplainer()
        limited = RateLimitedExplainer(mock, max_per_minute=1)

        snapshot = make_snapshot()
        assessment = make_assessment(snapshot)

        # First call succeeds
        limited.explain_assessment("T1", assessment, snapshot)

        # Manually clear the calls list to simulate time passing
        # (avoiding actual sleep in tests)
        limited._calls = []

        # Should succeed after "reset"
        explanation = limited.explain_assessment("T2", assessment, snapshot)
        assert len(explanation) > 0


class TestGetAvailableProviders:
    """Tests for get_available_providers."""

    def test_mock_always_available(self):
        """Mock provider should always be available."""
        available = ExplainerFactory.get_available_providers()
        assert "mock" in available

    def test_ollama_available_without_api_key(self):
        """Ollama should be available without API key (local server)."""
        available = ExplainerFactory.get_available_providers()
        assert "ollama" in available
