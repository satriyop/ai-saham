"""
Keyword-based headline classifier.

Rule-based sentiment classification using keyword matching.
Supports both Indonesian and English keywords.

Layer: Infrastructure
"""

import re

from src.domain.value_objects.sentiment import Sentiment

# Indonesian + English keywords (case-insensitive)
POSITIVE_KEYWORDS = [
    # Indonesian
    "naik",
    "untung",
    "profit",
    "laba",
    "positif",
    "surplus",
    "melonjak",
    "melesat",
    "menguat",
    "tumbuh",
    "cerah",
    "optimis",
    "bullish",
    "rekor",
    "tertinggi",
    "meningkat",
    "kinerja",
    "dividen",
    "akuisisi",
    "ekspansi",
    # English
    "gain",
    "growth",
    "rise",
    "surge",
    "jump",
    "bullish",
    "record",
    "high",
    "strong",
    "beat",
    "up",
    "rally",
    "soar",
    "climb",
    "boost",
]

NEGATIVE_KEYWORDS = [
    # Indonesian
    "turun",
    "rugi",
    "loss",
    "negatif",
    "defisit",
    "anjlok",
    "merosot",
    "jatuh",
    "melemah",
    "koreksi",
    "pesimis",
    "bearish",
    "terendah",
    "tekanan",
    "gagal",
    "bangkrut",
    "pailit",
    "krisis",
    "resesi",
    # English
    "drop",
    "fall",
    "decline",
    "bearish",
    "low",
    "weak",
    "pressure",
    "crash",
    "plunge",
    "miss",
    "down",
    "sink",
    "tumble",
    "slump",
    "risk",
]


class KeywordClassifier:
    """Rule-based headline classifier using keyword matching.

    Implements the HeadlineClassifier protocol using simple keyword
    matching. No external dependencies, fully deterministic.

    Usage:
        classifier = KeywordClassifier()
        sentiment = classifier.classify("BBCA catat laba bersih naik 10%")
        # Returns Sentiment.POSITIVE
    """

    def __init__(
        self,
        positive_keywords: list[str] | None = None,
        negative_keywords: list[str] | None = None,
    ):
        """Initialize classifier with keyword sets.

        Args:
            positive_keywords: Custom positive keywords (default: built-in list).
                              Pass explicit empty list [] to disable positive matching.
            negative_keywords: Custom negative keywords (default: built-in list).
                              Pass explicit empty list [] to disable negative matching.
        """
        # Use 'is None' check to allow explicit empty lists
        self._positive = frozenset(
            k.lower() for k in (POSITIVE_KEYWORDS if positive_keywords is None else positive_keywords)
        )
        self._negative = frozenset(
            k.lower() for k in (NEGATIVE_KEYWORDS if negative_keywords is None else negative_keywords)
        )

    @property
    def classifier_name(self) -> str:
        """Return classifier identifier."""
        return "keyword"

    def classify(self, headline: str) -> Sentiment:
        """Classify headline using keyword matching.

        Algorithm:
        1. Extract words from headline (lowercase)
        2. Count positive and negative keyword matches
        3. Higher count wins; tie defaults to NEUTRAL

        Args:
            headline: The headline text to classify

        Returns:
            Sentiment classification
        """
        # Normalize: lowercase, extract words using word boundaries
        words = frozenset(re.findall(r"\b\w+\b", headline.lower()))

        positive_matches = len(words & self._positive)
        negative_matches = len(words & self._negative)

        if positive_matches > negative_matches:
            return Sentiment.POSITIVE
        elif negative_matches > positive_matches:
            return Sentiment.NEGATIVE
        else:
            return Sentiment.NEUTRAL

    def classify_batch(self, headlines: list[str]) -> list[Sentiment]:
        """Classify multiple headlines.

        Args:
            headlines: List of headline texts to classify

        Returns:
            List of Sentiment classifications in same order
        """
        return [self.classify(h) for h in headlines]
