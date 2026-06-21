"""
Sentiment-related value objects.

Value objects for news sentiment analysis. These are purely informational
and do NOT affect risk assessment calculations.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Sentiment(Enum):
    """Sentiment classification for a headline."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class CatalystType(Enum):
    """Category of the news catalyst."""

    EARNINGS = "earnings"
    CORP_ACTION = "corp_action"
    REGULATORY = "regulatory"
    MACRO = "macro"
    GOVERNANCE = "governance"
    RUMOR = "rumor"
    GENERAL = "general"


@dataclass(frozen=True)
class Classification:
    """Combined sentiment and catalyst classification."""

    sentiment: Sentiment
    catalyst: CatalystType


@dataclass(frozen=True)
class HeadlineResult:
    """Single classified headline.

    Immutable value object representing a news headline with its
    sentiment and catalyst classification.
    """

    title: str
    source: str
    published: datetime
    sentiment: Sentiment
    catalyst: CatalystType = CatalystType.GENERAL
    url: str = ""

    def __post_init__(self) -> None:
        """Validate headline result."""
        if not self.title:
            raise ValueError("Headline title cannot be empty")
        if not self.source:
            raise ValueError("Headline source cannot be empty")


@dataclass(frozen=True)
class SentimentSnapshot:
    """Aggregated sentiment from multiple headlines.

    Immutable value object representing a point-in-time snapshot of
    sentiment analysis for a stock ticker.
    """

    ticker: str
    headlines: tuple[HeadlineResult, ...]
    positive_count: int
    neutral_count: int
    negative_count: int
    overall_sentiment: Sentiment
    fetched_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate snapshot data."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.positive_count < 0:
            raise ValueError("Positive count cannot be negative")
        if self.neutral_count < 0:
            raise ValueError("Neutral count cannot be negative")
        if self.negative_count < 0:
            raise ValueError("Negative count cannot be negative")

    @property
    def total_count(self) -> int:
        """Total number of headlines analyzed."""
        return self.positive_count + self.neutral_count + self.negative_count

    @property
    def confidence_pct(self) -> int:
        """Percentage of headlines matching overall sentiment."""
        if self.total_count == 0:
            return 0
        counts = {
            Sentiment.POSITIVE: self.positive_count,
            Sentiment.NEUTRAL: self.neutral_count,
            Sentiment.NEGATIVE: self.negative_count,
        }
        return int(counts[self.overall_sentiment] / self.total_count * 100)

    @property
    def score(self) -> float:
        """Numerical sentiment score (0.0 to 1.0)."""
        return float(self.confidence_pct) / 100.0

    @property
    def primary_catalyst(self) -> CatalystType:
        """Determine the primary catalyst type by majority vote."""
        if not self.headlines:
            return CatalystType.GENERAL

        cat_counts: dict[CatalystType, int] = {}
        for h in self.headlines:
            cat_counts[h.catalyst] = cat_counts.get(h.catalyst, 0) + 1

        return max(cat_counts, key=cat_counts.get) if cat_counts else CatalystType.GENERAL

    @classmethod
    def empty(cls, ticker: str) -> "SentimentSnapshot":
        """Create empty snapshot for when no news found."""
        return cls(
            ticker=ticker.upper(),
            headlines=(),
            positive_count=0,
            neutral_count=0,
            negative_count=0,
            overall_sentiment=Sentiment.NEUTRAL,
            fetched_at=datetime.now(),
        )

    @classmethod
    def from_headlines(
        cls,
        ticker: str,
        headlines: list[HeadlineResult],
    ) -> "SentimentSnapshot":
        """Create snapshot from classified headlines with majority vote.

        Uses simple majority voting to determine overall sentiment.
        In case of a tie, defaults to NEUTRAL.

        Args:
            ticker: Stock ticker symbol
            headlines: List of classified headlines

        Returns:
            SentimentSnapshot with aggregated counts and overall sentiment
        """
        positive = sum(1 for h in headlines if h.sentiment == Sentiment.POSITIVE)
        neutral = sum(1 for h in headlines if h.sentiment == Sentiment.NEUTRAL)
        negative = sum(1 for h in headlines if h.sentiment == Sentiment.NEGATIVE)

        # Simple majority vote
        if positive > neutral and positive > negative:
            overall = Sentiment.POSITIVE
        elif negative > neutral and negative > positive:
            overall = Sentiment.NEGATIVE
        else:
            overall = Sentiment.NEUTRAL

        return cls(
            ticker=ticker.upper(),
            headlines=tuple(headlines),
            positive_count=positive,
            neutral_count=neutral,
            negative_count=negative,
            overall_sentiment=overall,
            fetched_at=datetime.now(),
        )
