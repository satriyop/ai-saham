"""
Tests for KeywordClassifier.

These tests verify:
- Positive keyword detection (Indonesian and English)
- Negative keyword detection (Indonesian and English)
- Neutral classification for balanced/no keywords
- Case insensitivity
- Custom keyword support

All tests run offline with no external dependencies.
"""

from src.domain.value_objects.sentiment import Sentiment
from src.infrastructure.sentiment.keyword_classifier import (
    NEGATIVE_KEYWORDS,
    POSITIVE_KEYWORDS,
    KeywordClassifier,
)


class TestKeywordClassifierBasic:
    """Test basic KeywordClassifier functionality."""

    def test_classifier_name(self):
        """Classifier should have correct name."""
        classifier = KeywordClassifier()
        assert classifier.classifier_name == "keyword"


class TestPositiveClassification:
    """Test positive sentiment classification."""

    def test_indonesian_positive_keywords(self):
        """Indonesian positive keywords should classify as POSITIVE."""
        classifier = KeywordClassifier()

        # Test various Indonesian positive keywords
        assert classifier.classify("BBCA catat laba bersih naik 20%") == Sentiment.POSITIVE
        assert classifier.classify("Saham BBRI melonjak ke rekor tertinggi") == Sentiment.POSITIVE
        assert classifier.classify("Investor optimis sektor perbankan tumbuh") == Sentiment.POSITIVE
        assert classifier.classify("TLKM untung besar surplus kuartal ini") == Sentiment.POSITIVE

    def test_english_positive_keywords(self):
        """English positive keywords should classify as POSITIVE."""
        classifier = KeywordClassifier()

        assert classifier.classify("BBCA reports strong profit growth") == Sentiment.POSITIVE
        assert classifier.classify("Stock surge to record high") == Sentiment.POSITIVE
        assert classifier.classify("Bullish market rally continues") == Sentiment.POSITIVE
        assert classifier.classify("Company beat earnings expectations") == Sentiment.POSITIVE


class TestNegativeClassification:
    """Test negative sentiment classification."""

    def test_indonesian_negative_keywords(self):
        """Indonesian negative keywords should classify as NEGATIVE."""
        classifier = KeywordClassifier()

        assert classifier.classify("Saham BBCA anjlok 5% hari ini") == Sentiment.NEGATIVE
        assert classifier.classify("BBRI catat rugi besar kuartal III") == Sentiment.NEGATIVE
        assert classifier.classify("Sektor perbankan tertekan melemah") == Sentiment.NEGATIVE
        assert classifier.classify("Investor pesimis bearish saham turun") == Sentiment.NEGATIVE

    def test_english_negative_keywords(self):
        """English negative keywords should classify as NEGATIVE."""
        classifier = KeywordClassifier()

        assert classifier.classify("Stock crash amid market selloff") == Sentiment.NEGATIVE
        assert classifier.classify("Company reports significant loss") == Sentiment.NEGATIVE
        assert classifier.classify("Bearish pressure continues to plunge") == Sentiment.NEGATIVE
        assert classifier.classify("Shares decline on weak guidance") == Sentiment.NEGATIVE


class TestNeutralClassification:
    """Test neutral sentiment classification."""

    def test_no_keywords_is_neutral(self):
        """Headlines with no sentiment keywords should be NEUTRAL."""
        classifier = KeywordClassifier()

        assert classifier.classify("BBCA akan rapat pemegang saham") == Sentiment.NEUTRAL
        assert classifier.classify("Company announces new CEO appointment") == Sentiment.NEUTRAL
        assert classifier.classify("Market opens for trading today") == Sentiment.NEUTRAL

    def test_balanced_keywords_is_neutral(self):
        """Headlines with equal positive/negative keywords should be NEUTRAL."""
        classifier = KeywordClassifier()

        # One positive (naik), one negative (turun)
        assert classifier.classify("Saham naik kemudian turun") == Sentiment.NEUTRAL
        # One positive (profit), one negative (loss)
        assert classifier.classify("Profit offset by loss") == Sentiment.NEUTRAL


class TestCaseInsensitivity:
    """Test case insensitivity of classifier."""

    def test_uppercase_keywords_work(self):
        """Uppercase keywords should still be detected."""
        classifier = KeywordClassifier()

        assert classifier.classify("BBCA LABA NAIK BESAR") == Sentiment.POSITIVE
        assert classifier.classify("SAHAM ANJLOK RUGI") == Sentiment.NEGATIVE

    def test_mixed_case_keywords_work(self):
        """Mixed case keywords should still be detected."""
        classifier = KeywordClassifier()

        assert classifier.classify("Laba Naik Tertinggi") == Sentiment.POSITIVE
        assert classifier.classify("Saham Anjlok Melemah") == Sentiment.NEGATIVE


class TestMultipleKeywords:
    """Test classification with multiple keywords."""

    def test_more_positive_wins(self):
        """More positive keywords should result in POSITIVE."""
        classifier = KeywordClassifier()

        # 3 positive (naik, profit, tumbuh), 1 negative (turun)
        headline = "Laba naik profit meningkat tumbuh meski sempat turun"
        assert classifier.classify(headline) == Sentiment.POSITIVE

    def test_more_negative_wins(self):
        """More negative keywords should result in NEGATIVE."""
        classifier = KeywordClassifier()

        # 1 positive (naik), 3 negative (turun, rugi, anjlok)
        headline = "Saham naik sebentar lalu turun rugi anjlok"
        assert classifier.classify(headline) == Sentiment.NEGATIVE


class TestCustomKeywords:
    """Test custom keyword support."""

    def test_custom_positive_keywords(self):
        """Custom positive keywords should work."""
        classifier = KeywordClassifier(
            positive_keywords=["bagus", "hebat"],
            negative_keywords=["buruk", "jelek"],
        )

        assert classifier.classify("Kinerja bagus hebat") == Sentiment.POSITIVE
        assert classifier.classify("Hasil buruk jelek") == Sentiment.NEGATIVE
        # Default keywords should not work
        assert classifier.classify("Laba naik") == Sentiment.NEUTRAL

    def test_empty_custom_keywords(self):
        """Empty custom keywords should classify all as NEUTRAL."""
        classifier = KeywordClassifier(
            positive_keywords=[],
            negative_keywords=[],
        )

        assert classifier.classify("BBCA laba naik besar") == Sentiment.NEUTRAL
        assert classifier.classify("Saham anjlok rugi") == Sentiment.NEUTRAL


class TestClassifyBatch:
    """Test batch classification."""

    def test_classify_batch(self):
        """Batch classification should work correctly."""
        classifier = KeywordClassifier()

        headlines = [
            "BBCA laba naik 20%",
            "Pasar saham dibuka hari ini",
            "Saham anjlok tekanan jual",
        ]

        results = classifier.classify_batch(headlines)

        assert len(results) == 3
        assert results[0] == Sentiment.POSITIVE
        assert results[1] == Sentiment.NEUTRAL
        assert results[2] == Sentiment.NEGATIVE

    def test_classify_batch_empty(self):
        """Empty batch should return empty list."""
        classifier = KeywordClassifier()
        assert classifier.classify_batch([]) == []


class TestKeywordLists:
    """Test the default keyword lists."""

    def test_positive_keywords_not_empty(self):
        """Default positive keywords should not be empty."""
        assert len(POSITIVE_KEYWORDS) > 0

    def test_negative_keywords_not_empty(self):
        """Default negative keywords should not be empty."""
        assert len(NEGATIVE_KEYWORDS) > 0

    def test_no_overlap_in_keywords(self):
        """Positive and negative keywords should not overlap."""
        positive_set = set(k.lower() for k in POSITIVE_KEYWORDS)
        negative_set = set(k.lower() for k in NEGATIVE_KEYWORDS)
        overlap = positive_set & negative_set

        assert len(overlap) == 0, f"Overlapping keywords: {overlap}"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_headline(self):
        """Empty headline should be NEUTRAL."""
        classifier = KeywordClassifier()
        assert classifier.classify("") == Sentiment.NEUTRAL

    def test_whitespace_only_headline(self):
        """Whitespace-only headline should be NEUTRAL."""
        classifier = KeywordClassifier()
        assert classifier.classify("   \t\n  ") == Sentiment.NEUTRAL

    def test_special_characters(self):
        """Headlines with special characters should work."""
        classifier = KeywordClassifier()

        assert classifier.classify("BBCA +2% naik!!!") == Sentiment.POSITIVE
        assert classifier.classify("[BREAKING] Saham anjlok -5%") == Sentiment.NEGATIVE

    def test_numbers_in_headline(self):
        """Headlines with numbers should work."""
        classifier = KeywordClassifier()

        assert classifier.classify("Laba Q3 2024 naik 50%") == Sentiment.POSITIVE
        assert classifier.classify("Rugi Rp 100 miliar di 2024") == Sentiment.NEGATIVE

    def test_long_headline(self):
        """Long headlines should work."""
        classifier = KeywordClassifier()

        long_headline = (
            "PT Bank Central Asia Tbk (BBCA) mencatatkan pertumbuhan laba bersih "
            "yang naik signifikan sebesar 20% year-over-year pada kuartal ketiga "
            "2024 didorong oleh peningkatan pendapatan bunga bersih dan efisiensi "
            "operasional yang lebih baik di tengah kondisi ekonomi yang menantang"
        )

        assert classifier.classify(long_headline) == Sentiment.POSITIVE
