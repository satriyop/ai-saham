"""
Katadata news provider.

Fetches financial headlines from Katadata's Bursa (stock market) RSS feed.
Katadata is one of Indonesia's most respected financial data and news
platforms, covering IDX stocks, corporate actions, and market commentary.

No API key required. Ticker filtering is done locally on the headline text.

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

KATADATA_RSS_URL = "https://katadata.co.id/rss/finansial/bursa"
DEFAULT_TIMEOUT = 10
MAX_TITLE_LENGTH = 500
USER_AGENT = "ai-saham/1.0"


class KatadataNewsProvider:
    """Fetches IDX-relevant headlines from Katadata Bursa RSS.

    Katadata covers IDX stocks, earnings, dividends, IPOs, and market news.
    Headlines are filtered client-side: only items mentioning the ticker
    in title or description are returned.

    Usage:
        provider = KatadataNewsProvider()
        headlines = provider.fetch_headlines("BBCA", max_headlines=10, days=7)
    """

    @property
    def provider_name(self) -> str:
        return "katadata"

    def fetch_headlines(
        self,
        ticker: str,
        max_headlines: int = 20,
        days: int = 7,
    ) -> list[RawHeadline]:
        """Fetch Katadata headlines mentioning the ticker.

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
            req = Request(KATADATA_RSS_URL, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                xml_content = resp.read()
        except (URLError, HTTPError) as e:
            logger.warning("Katadata RSS unavailable: %s", e)
            return []

        try:
            return self._parse_rss(xml_content, ticker_upper, cutoff, max_headlines)
        except ET.ParseError as e:
            logger.warning("Failed to parse Katadata RSS: %s", e)
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

            if ticker not in combined:
                continue

            title = unescape(raw_title)[:MAX_TITLE_LENGTH]
            link = item.findtext("link", "")
            pub_date = self._parse_date(item.findtext("pubDate", ""))

            if pub_date and pub_date >= cutoff:
                headlines.append(
                    RawHeadline(
                        title=title,
                        source="Katadata",
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
