"""
Kontan news provider.

Fetches financial headlines from Kontan RSS feed.
Kontan is Indonesia's leading financial newspaper and the primary source
for IDX stock news, analyst recommendations, and corporate announcements.

No API key required. Filtering is done locally (RSS has no per-ticker search).

Layer: Infrastructure
"""

import logging
from datetime import datetime, timedelta
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import defusedxml.ElementTree as ET

from src.domain.ports.news_provider import RawHeadline

logger = logging.getLogger("ai_saham.sentiment")

KONTAN_RSS_URL = "https://investasi.kontan.co.id/rss"
DEFAULT_TIMEOUT = 10
MAX_TITLE_LENGTH = 500
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class KontanNewsProvider:
    """Fetches IDX-relevant headlines from Kontan RSS.

    Kontan covers IDX stocks, earnings, dividends, and analyst views.
    Headlines are filtered client-side: only items mentioning the ticker
    (or company name keywords) are returned.

    Usage:
        provider = KontanNewsProvider()
        headlines = provider.fetch_headlines("BBCA", max_headlines=10, days=7)
    """

    @property
    def provider_name(self) -> str:
        return "kontan"

    def fetch_headlines(
        self,
        ticker: str,
        max_headlines: int = 20,
        days: int = 7,
    ) -> list[RawHeadline]:
        """Fetch Kontan headlines mentioning the ticker.

        Args:
            ticker: IDX ticker symbol (e.g., "BBCA")
            max_headlines: Maximum headlines to return
            days: Look-back window in days

        Returns:
            List of raw headlines. Returns empty list on any error.
        """
        cutoff = datetime.now() - timedelta(days=days)
        ticker_upper = ticker.upper()

        try:
            req = Request(KONTAN_RSS_URL, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                xml_content = resp.read()
        except (URLError, HTTPError) as e:
            logger.warning("Kontan RSS unavailable: %s", e)
            return []

        try:
            return self._parse_rss(xml_content, ticker_upper, cutoff, max_headlines)
        except ET.ParseError as e:
            logger.warning("Failed to parse Kontan RSS: %s", e)
            return []

    def _parse_rss(
        self,
        xml_content: bytes,
        ticker: str,
        cutoff: datetime,
        max_headlines: int,
    ) -> list[RawHeadline]:
        root = ET.fromstring(xml_content)
        headlines: list[RawHeadline] = []

        for item in root.findall(".//item"):
            if len(headlines) >= max_headlines:
                break

            raw_title = item.findtext("title", "")
            description = item.findtext("description", "")
            combined = f"{raw_title} {description}".upper()

            # Only include items mentioning the ticker
            if ticker not in combined:
                continue

            title = unescape(raw_title)[:MAX_TITLE_LENGTH]
            link = item.findtext("link", "")
            pub_date = self._parse_date(item.findtext("pubDate", ""))

            if pub_date and pub_date >= cutoff:
                headlines.append(
                    RawHeadline(
                        title=title,
                        source="Kontan",
                        published=pub_date,
                        url=link,
                    )
                )

        return headlines

    def _parse_date(self, date_str: str) -> datetime | None:
        formats = [
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=None)
            except ValueError:
                continue
        return None
