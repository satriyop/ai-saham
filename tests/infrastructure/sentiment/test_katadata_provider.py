"""
Tests for KatadataNewsProvider.

These tests verify:
- Provider name is correct
- RSS parsing with ticker filtering
- Graceful degradation on network errors
- Date parsing for various formats
- Max headlines limit works
- Days look-back filtering

All tests run offline with mocked HTTP responses.
"""

from datetime import datetime
from unittest.mock import patch

from src.infrastructure.sentiment.katadata_provider import KatadataNewsProvider

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title><![CDATA[IHSG Ditutup Naik, Saham BBCA dan BMRI Diburu Investor]]></title>
    <link>https://katadata.co.id/finansial/bursa/1</link>
    <pubDate>Sun, 28 Jun 2026 16:44:00 +0700</pubDate>
    <description>IHSG ditutup naik didorong saham BBCA dan BMRI</description>
  </item>
  <item>
    <title><![CDATA[BEI Turunkan Bobot Saham GOTO di IHSG]]></title>
    <link>https://katadata.co.id/finansial/bursa/2</link>
    <pubDate>Sun, 28 Jun 2026 15:31:00 +0700</pubDate>
    <description>Bursa Efek Indonesia turunkan bobot GOTO</description>
  </item>
  <item>
    <title><![CDATA[IHSG Akhir Pekan Ditutup Turun, Saham EMAS dan DEWA Merosot]]></title>
    <link>https://katadata.co.id/finansial/bursa/3</link>
    <pubDate>Sun, 28 Jun 2026 14:42:00 +0700</pubDate>
    <description>IHSG turun, saham EMAS dan DEWA merosot tajam</description>
  </item>
</channel>
</rss>
"""


class TestKatadataProviderBasic:
    """Test basic KatadataNewsProvider functionality."""

    def test_provider_name(self):
        """Provider should have correct name."""
        provider = KatadataNewsProvider()
        assert provider.provider_name == "katadata"


class TestRSSParsing:
    """Test RSS parsing logic in isolation."""

    def test_parse_ticker_match(self):
        """Should find headlines mentioning the ticker."""
        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 1
        assert "BBCA" in headlines[0].title
        assert headlines[0].source == "Katadata"
        assert headlines[0].url.startswith("https://katadata.co.id")

    def test_parse_multiple_tickers(self):
        """Should find headlines for different tickers."""
        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 1, 1)

        goto = provider._parse_rss(SAMPLE_RSS.encode(), "GOTO", cutoff, 10)
        assert len(goto) == 1
        assert "GOTO" in goto[0].title

        emas = provider._parse_rss(SAMPLE_RSS.encode(), "EMAS", cutoff, 10)
        assert len(emas) == 1
        assert "EMAS" in emas[0].title

    def test_parse_no_match(self):
        """Should return empty list if no headlines mention ticker."""
        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "UNVR", cutoff, 10)

        assert len(headlines) == 0

    def test_parse_max_headlines(self):
        """Should respect max_headlines limit."""
        items = []
        for i in range(5):
            items.append(f"""  <item>
    <title><![CDATA[BBCA Headline {i}]]></title>
    <link>https://katadata.co.id/{i}</link>
    <pubDate>Sun, 28 Jun 2026 10:00:00 +0700</pubDate>
    <description>BBCA news {i}</description>
  </item>""")

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
{chr(10).join(items)}
</channel>
</rss>"""

        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(rss.encode(), "BBCA", cutoff, 3)

        assert len(headlines) == 3

    def test_parse_date_filtering(self):
        """Headlines older than cutoff should be excluded."""
        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 6, 29)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 0


class TestDateParsing:
    """Test date parsing for various formats."""

    def test_parse_date_with_timezone(self):
        """Should parse date with timezone offset."""
        provider = KatadataNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 16:44:00 +0700")
        assert result is not None
        assert result == datetime(2026, 6, 28, 16, 44, 0)

    def test_parse_date_with_zone_name(self):
        """Should parse date with timezone name."""
        provider = KatadataNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 16:44:00 WIB")
        assert result is not None
        assert result == datetime(2026, 6, 28, 16, 44, 0)

    def test_parse_date_no_timezone(self):
        """Should parse date without timezone."""
        provider = KatadataNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 16:44:00")
        assert result is not None
        assert result == datetime(2026, 6, 28, 16, 44, 0)

    def test_parse_date_invalid(self):
        """Should return None for unparseable date."""
        provider = KatadataNewsProvider()
        result = provider._parse_date("not a date")
        assert result is None

    def test_parse_date_empty(self):
        """Should return None for empty date."""
        provider = KatadataNewsProvider()
        result = provider._parse_date("")
        assert result is None


class TestNetworkErrors:
    """Test graceful degradation on network failures."""

    @patch("src.infrastructure.sentiment.katadata_provider.urlopen")
    def test_http_error(self, mock_urlopen):
        """Should return empty list on HTTP error."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "https://katadata.co.id/rss/finansial/bursa", 500, "Internal Server Error", {}, None
        )

        provider = KatadataNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0

    @patch("src.infrastructure.sentiment.katadata_provider.urlopen")
    def test_url_error(self, mock_urlopen):
        """Should return empty list on URL error."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")

        provider = KatadataNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0

    @patch("src.infrastructure.sentiment.katadata_provider.urlopen")
    def test_timeout(self, mock_urlopen):
        """Should return empty list on timeout."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("timed out")

        provider = KatadataNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0


class TestHeadlineDefaults:
    """Test headline default values."""

    def test_default_url_empty(self):
        """URL should default to empty string if missing."""
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title><![CDATA[BBCA Saham Naik]]></title>
    <pubDate>Sun, 28 Jun 2026 10:00:00 +0700</pubDate>
    <description>BBCA naik signifikan</description>
  </item>
</channel>
</rss>"""

        provider = KatadataNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(rss.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 1
        assert headlines[0].url == ""


class TestIntegrationWithComposite:
    """Test that provider integrates correctly with factory and composite."""

    def test_factory_creates_provider(self):
        """Factory should create Katadata provider."""
        from src.infrastructure.sentiment.factory import SentimentFactory

        provider = SentimentFactory.create_news_provider("katadata")
        assert provider.provider_name == "katadata"
        assert isinstance(provider, KatadataNewsProvider)

    def test_composite_includes_katadata(self):
        """Composite provider should include Katadata."""
        from src.infrastructure.sentiment.composite_provider import CompositeNewsProvider

        composite = CompositeNewsProvider()
        assert hasattr(composite, "_katadata")
        assert isinstance(composite._katadata, KatadataNewsProvider)
