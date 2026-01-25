"""
News provider port.

Abstract interface for fetching news headlines. Infrastructure layer
provides concrete implementations (Google News RSS, mock, etc.).

Layer: Domain
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawHeadline:
    """Raw headline from news source (before classification).

    This is a domain value object representing unclassified news data.
    """

    title: str
    source: str
    published: datetime
    url: str = ""

    def __post_init__(self) -> None:
        """Validate raw headline."""
        if not self.title:
            raise ValueError("Headline title cannot be empty")


class NewsProviderError(Exception):
    """Base exception for news provider errors."""

    pass


class NewsProvider(Protocol):
    """Port for fetching news headlines.

    This is a domain port (interface) that infrastructure adapters
    must implement. The domain layer depends on this abstraction,
    not concrete implementations.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        ...

    def fetch_headlines(
        self,
        ticker: str,
        max_headlines: int = 20,
        days: int = 3,
    ) -> list[RawHeadline]:
        """Fetch recent headlines for a ticker.

        Args:
            ticker: Stock ticker symbol
            max_headlines: Maximum headlines to return (default: 20)
            days: Number of days to look back (default: 3)

        Returns:
            List of raw headlines (not yet classified).
            Returns empty list on failure (graceful degradation).
        """
        ...
