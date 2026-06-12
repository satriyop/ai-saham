"""
Google News RSS provider.

Fetches news headlines from Google News RSS feed.
No API key required, but subject to rate limiting.

Layer: Infrastructure
"""

import logging
import defusedxml.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.domain.ports.news_provider import RawHeadline

logger = logging.getLogger("ai_saham.sentiment")

# Google News RSS configuration
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
DEFAULT_TIMEOUT = 10  # seconds
MAX_TITLE_LENGTH = 500  # Truncate long titles
USER_AGENT = "ai-saham/1.0"


class GoogleNewsProvider:
    """Fetches headlines from Google News RSS.

    Uses Google News RSS API which is freely available without authentication.
    Headlines are fetched in Indonesian language context for IDX stocks.

    Network Hardening:
    - 10 second timeout to prevent hanging
    - No retries (fail fast, show warning)
    - Title truncation to prevent memory issues
    - Graceful error handling (returns empty list on failure)

    Usage:
        provider = GoogleNewsProvider()
        headlines = provider.fetch_headlines("BBCA", max_headlines=10, days=3)
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize provider.

        Args:
            timeout: HTTP request timeout in seconds (default: 10)
        """
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "google_news"

    def fetch_headlines(
        self,
        ticker: str,
        max_headlines: int = 20,
        days: int = 3,
    ) -> list[RawHeadline]:
        """Fetch headlines from Google News RSS.

        Args:
            ticker: Stock ticker symbol (e.g., "BBCA")
            max_headlines: Maximum headlines to return (default: 20)
            days: Number of days to look back (default: 3)

        Returns:
            List of raw headlines. Returns empty list on any error.
        """
        url = self._build_url(ticker)
        cutoff = datetime.now() - timedelta(days=days)

        try:
            xml_content = self._fetch_rss(url)
            headlines = self._parse_rss(xml_content, cutoff, max_headlines)
            logger.info(f"Fetched {len(headlines)} headlines for {ticker}")
            return headlines

        except URLError as e:
            logger.warning(f"Network error fetching news for {ticker}: {e}")
            return []
        except HTTPError as e:
            logger.warning(f"HTTP error fetching news for {ticker}: {e.code}")
            return []
        except ET.ParseError as e:
            logger.warning(f"Failed to parse RSS for {ticker}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error fetching news for {ticker}: {e}")
            return []

    def _build_url(self, ticker: str) -> str:
        """Build Google News RSS URL for Indonesian stock.

        Searches for ticker + "saham" (Indonesian for "stock")
        in Indonesian language context. Properly URL-encodes the query.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Full RSS URL
        """
        import urllib.parse
        # "saham" = stock in Indonesian, helps filter relevant results
        query = f"{ticker} saham"
        encoded_query = urllib.parse.quote_plus(query)
        # hl=id (Indonesian), gl=ID (Indonesia), ceid=ID:id (Indonesia context)
        return f"{GOOGLE_NEWS_RSS_URL}?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"

    def _fetch_rss(self, url: str) -> bytes:
        """Fetch RSS content with timeout.

        Args:
            url: RSS feed URL

        Returns:
            Raw XML content as bytes

        Raises:
            URLError: On network error
            HTTPError: On HTTP error
        """
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=self._timeout) as response:
            return response.read()

    def _parse_rss(
        self,
        xml_content: bytes,
        cutoff: datetime,
        max_headlines: int,
    ) -> list[RawHeadline]:
        """Parse RSS XML and extract headlines.

        Args:
            xml_content: Raw XML bytes
            cutoff: Only include headlines after this datetime
            max_headlines: Maximum headlines to return

        Returns:
            List of parsed headlines within date range
        """
        root = ET.fromstring(xml_content)
        headlines: list[RawHeadline] = []

        for item in root.findall(".//item"):
            if len(headlines) >= max_headlines:
                break

            # Extract and clean title
            raw_title = item.findtext("title", "")
            title = self._clean_title(raw_title)[:MAX_TITLE_LENGTH]

            if not title:
                continue

            # Extract source (may be embedded in title or separate element)
            source = item.findtext("source", "")
            if not source:
                # Google News often appends " - Source" to title
                source = self._extract_source_from_title(raw_title)

            link = item.findtext("link", "")
            pub_date = self._parse_date(item.findtext("pubDate", ""))

            # Only include if within date range
            if pub_date and pub_date >= cutoff:
                headlines.append(
                    RawHeadline(
                        title=title,
                        source=source or "Unknown",
                        published=pub_date,
                        url=link,
                    )
                )

        return headlines

    def _clean_title(self, title: str) -> str:
        """Clean HTML entities and extra whitespace from title.

        Args:
            title: Raw title text

        Returns:
            Cleaned title
        """
        # Unescape HTML entities (e.g., &amp; -> &)
        cleaned = unescape(title)
        # Normalize whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _extract_source_from_title(self, title: str) -> str:
        """Extract source name from Google News title format.

        Google News often formats titles as "Headline - Source Name"

        Args:
            title: Raw title text

        Returns:
            Source name or empty string if not found
        """
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2:
                return parts[1].strip()
        return ""

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse RSS date format.

        Google News uses RFC 822 format: "Mon, 15 Jan 2024 10:30:00 GMT"

        Args:
            date_str: Date string from RSS

        Returns:
            Parsed datetime or None if parsing fails
        """
        # Common RFC 822 formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %Z",  # With timezone name
            "%a, %d %b %Y %H:%M:%S %z",  # With timezone offset
            "%a, %d %b %Y %H:%M:%S",  # Without timezone
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Last resort: try to parse just the date portion
        try:
            # Extract date part: "Mon, 15 Jan 2024"
            parts = date_str.split()
            if len(parts) >= 4:
                date_part = " ".join(parts[1:4])
                return datetime.strptime(date_part, "%d %b %Y")
        except (ValueError, IndexError):
            pass

        logger.debug(f"Failed to parse date: {date_str}")
        return None
