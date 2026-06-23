"""
Tests for FetchSentimentUseCase.

These tests verify:
- Use case orchestration of provider and classifier
- Response structure and metadata
- Caching behavior
- Warning messages for no news
- Integration with mock provider and keyword classifier

All tests run offline with no external dependencies.
"""

from datetime import datetime, timedelta

import pytest

from src.application.use_case.fetch_sentiment_use_case import (
    FetchSentimentRequest,
    FetchSentimentResponse,
    FetchSentimentUseCase,
)
from src.domain.ports.news_provider import RawHeadline
from src.domain.value_objects.sentiment import Sentiment, SentimentSnapshot
from src.infrastructure.sentiment.keyword_classifier import KeywordClassifier
from src.infrastructure.sentiment.mock_provider import MockNewsProvider


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear use case cache before and after each test."""
    FetchSentimentUseCase.clear_cache()
    yield
    FetchSentimentUseCase.clear_cache()


class TestFetchSentimentBasic:
    """Test basic FetchSentimentUseCase functionality."""

    def test_execute_returns_response(self):
        """Execute should return FetchSentimentResponse."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert isinstance(response, FetchSentimentResponse)
        assert response.ticker == "BBCA"
        assert response.success is True

    def test_response_contains_snapshot(self):
        """Response should contain SentimentSnapshot."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert isinstance(response.snapshot, SentimentSnapshot)
        assert response.snapshot.ticker == "BBCA"

    def test_response_contains_metadata(self):
        """Response should contain provider and classifier names."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.provider == "mock"
        assert response.classifier == "keyword"


class TestTickerNormalization:
    """Test ticker normalization."""

    def test_ticker_is_uppercased(self):
        """Ticker should be uppercased in response."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="bbca"))

        assert response.ticker == "BBCA"
        assert response.snapshot.ticker == "BBCA"


class TestRequestParameters:
    """Test request parameters are passed correctly."""

    def test_max_headlines_passed(self):
        """max_headlines should limit results."""
        now = datetime.now()
        headlines = [
            RawHeadline(f"Headline {i}", "Source", now - timedelta(hours=i)) for i in range(10)
        ]
        provider = MockNewsProvider(headlines=headlines)
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA", max_headlines=3))

        assert response.snapshot.total_count == 3

    def test_days_parameter_passed(self):
        """days parameter should filter old headlines."""
        now = datetime.now()
        headlines = [
            RawHeadline("Recent", "Source", now),
            RawHeadline("Old", "Source", now - timedelta(days=10)),
        ]
        provider = MockNewsProvider(headlines=headlines)
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA", days=3))

        assert response.snapshot.total_count == 1


class TestClassification:
    """Test headline classification."""

    def test_positive_headlines_classified(self):
        """Positive headlines should be classified as POSITIVE."""
        now = datetime.now()
        headlines = [
            RawHeadline("BBCA laba naik 20%", "Kontan", now),
            RawHeadline("Saham melonjak rekor", "Bisnis", now),
        ]
        provider = MockNewsProvider(headlines=headlines)
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.snapshot.positive_count == 2
        assert response.snapshot.overall_sentiment == Sentiment.POSITIVE

    def test_negative_headlines_classified(self):
        """Negative headlines should be classified as NEGATIVE."""
        provider = MockNewsProvider.create_negative_set()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.snapshot.negative_count > 0
        assert response.snapshot.overall_sentiment == Sentiment.NEGATIVE

    def test_mixed_headlines_majority_wins(self):
        """Mixed headlines should use majority vote."""
        now = datetime.now()
        headlines = [
            RawHeadline("Laba naik", "A", now),  # positive
            RawHeadline("Profit up", "B", now),  # positive
            RawHeadline("Market update", "C", now),  # neutral
        ]
        provider = MockNewsProvider(headlines=headlines)
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.snapshot.overall_sentiment == Sentiment.POSITIVE


class TestNoNewsScenario:
    """Test behavior when no news is found."""

    def test_empty_headlines_returns_warning(self):
        """Empty headlines should return warning message."""
        provider = MockNewsProvider.create_empty()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.success is True
        assert response.warning is not None
        assert "No recent news found" in response.warning
        assert "BBCA" in response.warning

    def test_empty_headlines_returns_empty_snapshot(self):
        """Empty headlines should return empty snapshot."""
        provider = MockNewsProvider.create_empty()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.snapshot.total_count == 0
        assert response.snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_has_headlines_property_false(self):
        """has_headlines should be False for empty response."""
        provider = MockNewsProvider.create_empty()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response.has_headlines is False


class TestCaching:
    """Test caching behavior."""

    def test_same_day_request_uses_cache(self):
        """Same ticker on same day should use cache."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        # First request
        response1 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))
        # Second request
        response2 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response1.from_cache is False
        assert response2.from_cache is True

    def test_different_ticker_not_cached(self):
        """Different ticker should not use cache."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response1 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))
        response2 = use_case.execute(FetchSentimentRequest(ticker="BBRI"))

        assert response1.from_cache is False
        assert response2.from_cache is False

    def test_clear_cache(self):
        """clear_cache should clear cached results."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        # First request
        response1 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))
        # Clear cache
        FetchSentimentUseCase.clear_cache()
        # Second request
        response2 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert response1.from_cache is False
        assert response2.from_cache is False

    def test_cache_key_includes_ticker_case(self):
        """Cache should treat same ticker case-insensitively."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response1 = use_case.execute(FetchSentimentRequest(ticker="bbca"))
        response2 = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        # Both should be BBCA (uppercased)
        assert response1.ticker == "BBCA"
        assert response2.ticker == "BBCA"
        # Second should use cache
        assert response2.from_cache is True


class TestHeadlineResultsInSnapshot:
    """Test that classified headlines are stored in snapshot."""

    def test_headlines_stored_in_snapshot(self):
        """Classified headlines should be stored in snapshot."""
        now = datetime.now()
        headlines = [
            RawHeadline("Laba naik", "Kontan", now, "http://a.com"),
            RawHeadline("Rugi besar", "Bisnis", now, "http://b.com"),
        ]
        provider = MockNewsProvider(headlines=headlines)
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        assert len(response.snapshot.headlines) == 2
        # Check first headline
        h1 = response.snapshot.headlines[0]
        assert h1.title == "Laba naik"
        assert h1.source == "Kontan"
        assert h1.sentiment == Sentiment.POSITIVE
        # Check second headline
        h2 = response.snapshot.headlines[1]
        assert h2.title == "Rugi besar"
        assert h2.sentiment == Sentiment.NEGATIVE


class TestIntegrationWithDefaultProvider:
    """Integration test with default mock provider."""

    def test_full_flow_with_defaults(self):
        """Test full flow with default mock provider."""
        provider = MockNewsProvider()
        classifier = KeywordClassifier()
        use_case = FetchSentimentUseCase(
            news_provider=provider,
            classifier=classifier,
        )

        response = use_case.execute(FetchSentimentRequest(ticker="BBCA"))

        # Should have headlines
        assert response.has_headlines is True
        # Should have counts
        assert response.snapshot.total_count > 0
        # Should have valid sentiment
        assert response.snapshot.overall_sentiment in Sentiment
        # Should have metadata
        assert response.provider == "mock"
        assert response.classifier == "keyword"


class TestSentimentDoesNotAffectRisk:
    """Document that sentiment does NOT affect risk assessment.

    This is a documentation/design test to ensure sentiment layer
    remains purely informational.
    """

    def test_sentiment_snapshot_is_informational(self):
        """SentimentSnapshot should have no risk-related attributes."""
        snapshot = SentimentSnapshot.empty("BBCA")

        # Verify no risk-related attributes exist
        assert not hasattr(snapshot, "risk_level")
        assert not hasattr(snapshot, "risk_assessment")
        assert not hasattr(snapshot, "confidence_score")

        # Only has sentiment-related attributes
        assert hasattr(snapshot, "overall_sentiment")
        assert hasattr(snapshot, "positive_count")
        assert hasattr(snapshot, "negative_count")
        assert hasattr(snapshot, "neutral_count")
