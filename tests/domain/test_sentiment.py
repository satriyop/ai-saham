"""
Tests for sentiment value objects.

These tests verify:
- Sentiment enum values
- HeadlineResult creation and validation
- SentimentSnapshot creation, aggregation, and majority vote logic
- Edge cases and error handling

All tests run offline with no external dependencies.
"""

from datetime import date, datetime

import pytest

from src.domain.value_objects.sentiment import (
    CatalystType,
    HeadlineResult,
    Sentiment,
    SentimentSnapshot,
)


class TestSentimentEnum:
    """Test Sentiment enumeration."""

    def test_sentiment_values(self):
        """Sentiment enum should have correct values."""
        assert Sentiment.POSITIVE.value == "POSITIVE"
        assert Sentiment.NEUTRAL.value == "NEUTRAL"
        assert Sentiment.NEGATIVE.value == "NEGATIVE"

    def test_sentiment_from_string(self):
        """Sentiment can parse canonical and legacy values."""
        assert Sentiment.parse("POSITIVE") == Sentiment.POSITIVE
        assert Sentiment.parse("positive") == Sentiment.POSITIVE
        assert Sentiment.parse("neutral") == Sentiment.NEUTRAL
        assert Sentiment.parse("negative") == Sentiment.NEGATIVE


class TestCatalystTypeEnum:
    """Test CatalystType enumeration."""

    def test_catalyst_values(self):
        """CatalystType enum should have correct values."""
        assert CatalystType.EARNINGS.value == "EARNINGS"
        assert CatalystType.RUMOR.value == "RUMOR"
        assert CatalystType.GENERAL.value == "GENERAL"

    def test_catalyst_from_string(self):
        """CatalystType can parse canonical and legacy values."""
        assert CatalystType.parse("EARNINGS") == CatalystType.EARNINGS
        assert CatalystType.parse("earnings") == CatalystType.EARNINGS
        assert CatalystType.parse("corp_action") == CatalystType.CORP_ACTION


class TestHeadlineResult:
    """Test HeadlineResult value object."""

    def test_create_valid_headline(self):
        """Valid headline should be created successfully."""
        now = datetime.now()
        headline = HeadlineResult(
            title="BBCA Laba Naik 20%",
            source="Kontan",
            published=now,
            sentiment=Sentiment.POSITIVE,
            catalyst=CatalystType.EARNINGS,
            url="https://example.com/news",
        )

        assert headline.title == "BBCA Laba Naik 20%"
        assert headline.source == "Kontan"
        assert headline.published == now
        assert headline.sentiment == Sentiment.POSITIVE
        assert headline.catalyst == CatalystType.EARNINGS
        assert headline.url == "https://example.com/news"

    def test_headline_defaults_to_general_catalyst(self):
        """HeadlineResult should default to GENERAL catalyst."""
        headline = HeadlineResult(
            title="Test",
            source="Test Source",
            published=datetime.now(),
            sentiment=Sentiment.NEUTRAL,
        )
        assert headline.catalyst == CatalystType.GENERAL

    def test_headline_is_immutable(self):
        """HeadlineResult should be immutable (frozen dataclass)."""
        headline = HeadlineResult(
            title="Test",
            source="Test Source",
            published=datetime.now(),
            sentiment=Sentiment.NEUTRAL,
        )

        with pytest.raises(AttributeError):
            headline.title = "Modified"

    def test_headline_with_empty_title_fails(self):
        """HeadlineResult with empty title should fail validation."""
        with pytest.raises(ValueError, match="title cannot be empty"):
            HeadlineResult(
                title="",
                source="Test Source",
                published=datetime.now(),
                sentiment=Sentiment.NEUTRAL,
            )

    def test_headline_with_empty_source_fails(self):
        """HeadlineResult with empty source should fail validation."""
        with pytest.raises(ValueError, match="source cannot be empty"):
            HeadlineResult(
                title="Test Title",
                source="",
                published=datetime.now(),
                sentiment=Sentiment.NEUTRAL,
            )

    def test_headline_url_is_optional(self):
        """HeadlineResult should allow empty URL."""
        headline = HeadlineResult(
            title="Test",
            source="Test Source",
            published=datetime.now(),
            sentiment=Sentiment.NEUTRAL,
        )
        assert headline.url == ""


class TestSentimentSnapshot:
    """Test SentimentSnapshot value object."""

    def test_create_valid_snapshot(self):
        """Valid snapshot should be created successfully."""
        snapshot = SentimentSnapshot(
            ticker="BBCA",
            headlines=(),
            positive_count=5,
            neutral_count=3,
            negative_count=2,
            overall_sentiment=Sentiment.POSITIVE,
        )

        assert snapshot.ticker == "BBCA"
        assert snapshot.positive_count == 5
        assert snapshot.neutral_count == 3
        assert snapshot.negative_count == 2
        assert snapshot.overall_sentiment == Sentiment.POSITIVE

    def test_snapshot_is_immutable(self):
        """SentimentSnapshot should be immutable."""
        snapshot = SentimentSnapshot.empty("BBCA")

        with pytest.raises(AttributeError):
            snapshot.positive_count = 10

    def test_empty_ticker_fails(self):
        """Empty ticker should fail validation."""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            SentimentSnapshot(
                ticker="",
                headlines=(),
                positive_count=0,
                neutral_count=0,
                negative_count=0,
                overall_sentiment=Sentiment.NEUTRAL,
            )

    def test_negative_counts_fail(self):
        """Negative counts should fail validation."""
        with pytest.raises(ValueError, match="cannot be negative"):
            SentimentSnapshot(
                ticker="BBCA",
                headlines=(),
                positive_count=-1,
                neutral_count=0,
                negative_count=0,
                overall_sentiment=Sentiment.NEUTRAL,
            )


class TestSentimentSnapshotTotalCount:
    """Test SentimentSnapshot total_count property."""

    def test_total_count_sum(self):
        """Total count should be sum of all sentiment counts."""
        snapshot = SentimentSnapshot(
            ticker="BBCA",
            headlines=(),
            positive_count=5,
            neutral_count=3,
            negative_count=2,
            overall_sentiment=Sentiment.POSITIVE,
        )

        assert snapshot.total_count == 10

    def test_total_count_zero(self):
        """Total count should be zero for empty snapshot."""
        snapshot = SentimentSnapshot.empty("BBCA")
        assert snapshot.total_count == 0


class TestSentimentSnapshotConfidence:
    """Test SentimentSnapshot confidence_pct property."""

    def test_confidence_majority(self):
        """Confidence should be percentage of majority sentiment."""
        snapshot = SentimentSnapshot(
            ticker="BBCA",
            headlines=(),
            positive_count=8,
            neutral_count=1,
            negative_count=1,
            overall_sentiment=Sentiment.POSITIVE,
        )

        assert snapshot.confidence_pct == 80  # 8/10 = 80%

    def test_confidence_zero_for_empty(self):
        """Confidence should be 0 for empty snapshot."""
        snapshot = SentimentSnapshot.empty("BBCA")
        assert snapshot.confidence_pct == 0


class TestSentimentSnapshotEmpty:
    """Test SentimentSnapshot.empty() factory method."""

    def test_empty_snapshot(self):
        """Empty snapshot should have zero counts and NEUTRAL sentiment."""
        snapshot = SentimentSnapshot.empty("BBCA")

        assert snapshot.ticker == "BBCA"
        assert snapshot.fetched_at is not None
        assert snapshot.fetched_at.date() == date.today()
        assert snapshot.headlines == ()
        assert snapshot.positive_count == 0
        assert snapshot.neutral_count == 0
        assert snapshot.negative_count == 0
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_empty_normalizes_ticker(self):
        """Empty snapshot should uppercase ticker."""
        snapshot = SentimentSnapshot.empty("bbca")
        assert snapshot.ticker == "BBCA"


class TestSentimentSnapshotFromHeadlines:
    """Test SentimentSnapshot.from_headlines() factory method."""

    def _make_headline(self, sentiment: Sentiment) -> HeadlineResult:
        """Helper to create test headline."""
        return HeadlineResult(
            title=f"Test headline {sentiment.value}",
            source="Test Source",
            published=datetime.now(),
            sentiment=sentiment,
            catalyst=CatalystType.GENERAL,
        )

    def test_from_headlines_majority_positive(self):
        """Majority positive headlines should result in POSITIVE overall."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEGATIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert snapshot.positive_count == 3
        assert snapshot.neutral_count == 1
        assert snapshot.negative_count == 1
        assert snapshot.overall_sentiment == Sentiment.POSITIVE

    def test_from_headlines_majority_negative(self):
        """Majority negative headlines should result in NEGATIVE overall."""
        headlines = [
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.POSITIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert snapshot.positive_count == 1
        assert snapshot.negative_count == 3
        assert snapshot.overall_sentiment == Sentiment.NEGATIVE

    def test_from_headlines_tie_defaults_to_neutral(self):
        """Tie in sentiment counts should default to NEUTRAL."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEGATIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert snapshot.positive_count == 1
        assert snapshot.negative_count == 1
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_from_headlines_all_neutral(self):
        """All neutral headlines should result in NEUTRAL overall."""
        headlines = [
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert snapshot.neutral_count == 3
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_from_headlines_empty_list(self):
        """Empty headline list should create empty snapshot."""
        snapshot = SentimentSnapshot.from_headlines("BBCA", [])

        assert snapshot.total_count == 0
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_from_headlines_normalizes_ticker(self):
        """from_headlines should uppercase ticker."""
        snapshot = SentimentSnapshot.from_headlines("bbca", [])
        assert snapshot.ticker == "BBCA"

    def test_from_headlines_stores_headlines(self):
        """from_headlines should store headlines as tuple."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert isinstance(snapshot.headlines, tuple)
        assert len(snapshot.headlines) == 2


class TestMajorityVoteEdgeCases:
    """Test majority vote algorithm edge cases."""

    def _make_headline(self, sentiment: Sentiment) -> HeadlineResult:
        """Helper to create test headline."""
        return HeadlineResult(
            title=f"Test headline {sentiment.value}",
            source="Test Source",
            published=datetime.now(),
            sentiment=sentiment,
            catalyst=CatalystType.GENERAL,
        )

    def test_positive_wins_over_neutral_tie_with_negative(self):
        """Positive should win when positive > neutral and positive > negative."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEGATIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        # positive=2, neutral=1, negative=1
        # 2 > 1 and 2 > 1, so POSITIVE wins
        assert snapshot.overall_sentiment == Sentiment.POSITIVE

    def test_negative_wins_over_neutral_tie_with_positive(self):
        """Negative should win when negative > neutral and negative > positive."""
        headlines = [
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        # positive=1, neutral=1, negative=2
        # 2 > 1 and 2 > 1, so NEGATIVE wins
        assert snapshot.overall_sentiment == Sentiment.NEGATIVE

    def test_neutral_majority(self):
        """Neutral should win when it has clear majority."""
        headlines = [
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEGATIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        # positive=1, neutral=3, negative=1
        # Neutral is highest, defaults to NEUTRAL anyway
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_three_way_tie(self):
        """Three-way tie should default to NEUTRAL."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEGATIVE),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_positive_neutral_tie_defaults_neutral(self):
        """Positive-neutral tie should default to NEUTRAL."""
        headlines = [
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.POSITIVE),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        # positive=2, neutral=2, negative=0
        # positive is NOT > neutral, so falls through to NEUTRAL
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL

    def test_negative_neutral_tie_defaults_neutral(self):
        """Negative-neutral tie should default to NEUTRAL."""
        headlines = [
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.NEGATIVE),
            self._make_headline(Sentiment.NEUTRAL),
            self._make_headline(Sentiment.NEUTRAL),
        ]

        snapshot = SentimentSnapshot.from_headlines("BBCA", headlines)

        # positive=0, neutral=2, negative=2
        # negative is NOT > neutral, so falls through to NEUTRAL
        assert snapshot.overall_sentiment == Sentiment.NEUTRAL
