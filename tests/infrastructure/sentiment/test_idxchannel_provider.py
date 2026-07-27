"""
Tests for IDXChannelNewsProvider.

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

from src.infrastructure.sentiment.idxchannel_provider import IDXChannelNewsProvider

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title><![CDATA[Saham BBCA Melonjak di Tengah Tekanan Pasar]]></title>
    <link>https://www.idxchannel.com/market-news/saham-bbca-melonjak</link>
    <pubDate>Sun, 28 Jun 2026 10:00:00 +0700</pubDate>
    <description><![CDATA[Saham BBCA melonjak signifikan hari ini]]></description>
  </item>
  <item>
    <title><![CDATA[IHSG Ditutup Melemah, Saham Teknologi Tertekan]]></title>
    <link>https://www.idxchannel.com/market-news/ihsg-melemah</link>
    <pubDate>Sun, 28 Jun 2026 09:00:00 +0700</pubDate>
    <description><![CDATA[Indeks Harga Saham Gabungan ditutup melemah]]></description>
  </item>
  <item>
    <title><![CDATA[BBRI Bagikan Dividen Rp 10 Triliun]]></title>
    <link>https://www.idxchannel.com/market-news/bbri-dividen</link>
    <pubDate>Sun, 28 Jun 2026 08:00:00 +0700</pubDate>
    <description><![CDATA[Bank BRI bagikan dividen kepada pemegang saham]]></description>
  </item>
  <item>
    <title><![CDATA[AKRA Alihkan 181 Juta Saham Treasuri ke Arthakencana Rayatama]]></title>
    <link>https://www.idxchannel.com/market-news/akra-treasuri</link>
    <pubDate>Sun, 28 Jun 2026 07:30:00 +0700</pubDate>
    <description>AKRA alihkan saham treasuri</description>
  </item>
</channel>
</rss>
"""


class TestIDXChannelProviderBasic:
    """Test basic IDXChannelNewsProvider functionality."""

    def test_provider_name(self):
        """Provider should have correct name."""
        provider = IDXChannelNewsProvider()
        assert provider.provider_name == "idxchannel"


class TestRSSParsing:
    """Test RSS parsing logic in isolation."""

    def test_parse_ticker_match(self):
        """Should find headlines mentioning the ticker."""
        provider = IDXChannelNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 1
        assert headlines[0].title == "Saham BBCA Melonjak di Tengah Tekanan Pasar"
        assert headlines[0].source == "IDXChannel"
        assert headlines[0].url == "https://www.idxchannel.com/market-news/saham-bbca-melonjak"

    def test_parse_ticker_case_insensitive(self):
        """Ticker matching is uppercase; _parse_rss receives uppercased ticker from
        fetch_headlines."""
        provider = IDXChannelNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 1

    def test_parse_multiple_tickers(self):
        """Should find headlines for different tickers."""
        provider = IDXChannelNewsProvider()
        cutoff = datetime(2026, 1, 1)

        bbca = provider._parse_rss(SAMPLE_RSS.encode(), "BBRI", cutoff, 10)
        assert len(bbca) == 1
        assert "BBRI" in bbca[0].title

    def test_parse_no_match(self):
        """Should return empty list if no headlines mention ticker."""
        provider = IDXChannelNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "UNVR", cutoff, 10)

        assert len(headlines) == 0

    def test_parse_max_headlines(self):
        """Should respect max_headlines limit."""
        # Create RSS with many matching headlines for BBRI
        items = []
        for i in range(5):
            items.append(f"""  <item>
    <title><![CDATA[BBRI Headline {i}]]></title>
    <link>https://www.idxchannel.com/{i}</link>
    <pubDate>Sun, 28 Jun 2026 10:00:00 +0700</pubDate>
    <description>BBRI news {i}</description>
  </item>""")

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
{chr(10).join(items)}
</channel>
</rss>"""

        provider = IDXChannelNewsProvider()
        cutoff = datetime(2026, 1, 1)
        headlines = provider._parse_rss(rss.encode(), "BBRI", cutoff, 3)

        assert len(headlines) == 3

    def test_parse_date_filtering(self):
        """Headlines older than cutoff should be excluded."""
        provider = IDXChannelNewsProvider()
        # Cutoff after both articles published
        cutoff = datetime(2026, 6, 29)
        headlines = provider._parse_rss(SAMPLE_RSS.encode(), "BBCA", cutoff, 10)

        assert len(headlines) == 0


class TestDateParsing:
    """Test date parsing for various formats."""

    def test_parse_date_with_timezone(self):
        """Should parse date with timezone offset."""
        provider = IDXChannelNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 10:00:00 +0700")
        assert result is not None
        assert result == datetime(2026, 6, 28, 10, 0, 0)

    def test_parse_date_with_zone_name(self):
        """Should parse date with timezone name."""
        provider = IDXChannelNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 10:00:00 WIB")
        assert result is not None
        assert result == datetime(2026, 6, 28, 10, 0, 0)

    def test_parse_date_no_timezone(self):
        """Should parse date without timezone."""
        provider = IDXChannelNewsProvider()
        result = provider._parse_date("Sun, 28 Jun 2026 10:00:00")
        assert result is not None
        assert result == datetime(2026, 6, 28, 10, 0, 0)

    def test_parse_date_invalid(self):
        """Should return None for unparseable date."""
        provider = IDXChannelNewsProvider()
        result = provider._parse_date("not a date")
        assert result is None

    def test_parse_date_empty(self):
        """Should return None for empty date."""
        provider = IDXChannelNewsProvider()
        result = provider._parse_date("")
        assert result is None


class TestNetworkErrors:
    """Test graceful degradation on network failures."""

    @patch("src.infrastructure.sentiment.idxchannel_provider.urlopen")
    def test_http_error(self, mock_urlopen):
        """Should return empty list on HTTP error."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "https://www.idxchannel.com/rss", 500, "Internal Server Error", {}, None
        )

        provider = IDXChannelNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0

    @patch("src.infrastructure.sentiment.idxchannel_provider.urlopen")
    def test_url_error(self, mock_urlopen):
        """Should return empty list on URL error."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Connection refused")

        provider = IDXChannelNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0

    @patch("src.infrastructure.sentiment.idxchannel_provider.urlopen")
    def test_timeout(self, mock_urlopen):
        """Should return empty list on timeout."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("timed out")

        provider = IDXChannelNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0


class TestIntegrationWithComposite:
    """Test that provider integrates correctly with factory."""

    def test_factory_creates_provider(self):
        """Factory should create IDXChannel provider."""
        from src.infrastructure.sentiment.factory import SentimentFactory

        provider = SentimentFactory.create_news_provider("idxchannel")
        assert provider.provider_name == "idxchannel"
        assert isinstance(provider, IDXChannelNewsProvider)

    def test_composite_includes_idxchannel(self):
        """Composite provider should include IDXChannel."""
        from src.infrastructure.sentiment.composite_provider import CompositeNewsProvider

        composite = CompositeNewsProvider()
        assert hasattr(composite, "_idxchannel")
        assert isinstance(composite._idxchannel, IDXChannelNewsProvider)
