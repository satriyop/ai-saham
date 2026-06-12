"""
Sentiment repository port.

Abstract interface for persisting sentiment logs and audit results.
Infrastructure layer provides concrete implementations (SQLite).

Layer: Domain (Port)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol

from src.domain.value_objects.sentiment import CatalystType, Sentiment


@dataclass(frozen=True)
class SentimentLog:
    """A single sentiment analysis record."""

    id: Optional[int]
    date: date
    ticker: str
    sentiment: Sentiment
    catalyst: CatalystType
    score: float  # confidence score (confidence_pct / 100)


@dataclass(frozen=True)
class SentimentAudit:
    """Price impact audit for a sentiment log."""

    log_id: int
    days_after: int  # 1, 3, or 5
    price_delta_pct: Decimal
    audited_at: date


class SentimentRepository(Protocol):
    """Port for persisting sentiment data and audits."""

    def save_log(self, log: SentimentLog) -> int:
        """Save a new sentiment log.

        Args:
            log: The sentiment log to save

        Returns:
            The unique ID of the saved log
        """
        ...

    def get_unaudited_logs(self, days_ago: int) -> list[SentimentLog]:
        """Find logs that haven't been audited for a specific timeframe.

        Args:
            days_ago: Minimum age of log in days (1, 3, or 5)

        Returns:
            List of logs ready for auditing
        """
        ...

    def save_audit(self, audit: SentimentAudit) -> None:
        """Save an audit result.

        Args:
            audit: The audit result to save
        """
        ...

    def get_stats(self) -> dict:
        """Get summary statistics for sentiment accuracy.

        Returns:
            Dict with win rates per sentiment and catalyst
        """
        ...
