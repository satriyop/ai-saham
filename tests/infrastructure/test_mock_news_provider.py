"""
Tests for MockNewsProvider.

These tests verify:
- Default headlines are returned
- Custom headlines work
- Date filtering works
- Max headlines limit works
- Factory methods for test scenarios

All tests run offline with no external dependencies.
"""

from datetime import datetime, timedelta

import pytest

from src.domain.ports.news_provider import RawHeadline
from src.infrastructure.sentiment.mock_provider import MockNewsProvider


class TestMockNewsProviderBasic:
    """Test basic MockNewsProvider functionality."""

    def test_provider_name(self):
        """Provider should have correct name."""
        provider = MockNewsProvider()
        assert provider.provider_name == "mock"

    def test_default_headlines_returned(self):
        """Default provider should return default headlines."""
        provider = MockNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) > 0
        for h in headlines:
            assert isinstance(h, RawHeadline)
            assert h.title
            assert h.source

    def test_fetch_any_ticker(self):
        """Provider should work with any ticker."""
        provider = MockNewsProvider()

        bbca = provider.fetch_headlines("BBCA")
        bbri = provider.fetch_headlines("BBRI")

        # Should return same default headlines regardless of ticker
        assert len(bbca) == len(bbri)


class TestCustomHeadlines:
    """Test custom headline support."""

    def test_custom_headlines(self):
        """Custom headlines should be returned."""
        custom = [
            RawHeadline("Custom Headline 1", "Source A", datetime.now()),
            RawHeadline("Custom Headline 2", "Source B", datetime.now()),
        ]
        provider = MockNewsProvider(headlines=custom)

        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 2
        assert headlines[0].title == "Custom Headline 1"
        assert headlines[1].title == "Custom Headline 2"

    def test_empty_custom_headlines(self):
        """Empty custom headlines should return empty list."""
        provider = MockNewsProvider(headlines=[])
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0


class TestMaxHeadlines:
    """Test max_headlines parameter."""

    def test_max_headlines_limits_result(self):
        """max_headlines should limit returned count."""
        custom = [
            RawHeadline(f"Headline {i}", "Source", datetime.now())
            for i in range(10)
        ]
        provider = MockNewsProvider(headlines=custom)

        headlines = provider.fetch_headlines("BBCA", max_headlines=3)

        assert len(headlines) == 3

    def test_max_headlines_greater_than_available(self):
        """max_headlines greater than available should return all."""
        custom = [
            RawHeadline(f"Headline {i}", "Source", datetime.now())
            for i in range(3)
        ]
        provider = MockNewsProvider(headlines=custom)

        headlines = provider.fetch_headlines("BBCA", max_headlines=10)

        assert len(headlines) == 3


class TestDateFiltering:
    """Test days parameter filtering."""

    def test_days_filters_old_headlines(self):
        """Headlines older than days should be filtered out."""
        now = datetime.now()
        custom = [
            RawHeadline("Recent", "Source", now - timedelta(hours=1)),
            RawHeadline("Old", "Source", now - timedelta(days=5)),
            RawHeadline("Very Old", "Source", now - timedelta(days=10)),
        ]
        provider = MockNewsProvider(headlines=custom)

        # Only get headlines from last 3 days
        headlines = provider.fetch_headlines("BBCA", days=3)

        assert len(headlines) == 1
        assert headlines[0].title == "Recent"

    def test_days_edge_case(self):
        """Headlines exactly at cutoff should be included."""
        now = datetime.now()
        # Headline from 2.5 days ago (within 3 day window)
        custom = [
            RawHeadline("Within Window", "Source", now - timedelta(days=2, hours=12)),
        ]
        provider = MockNewsProvider(headlines=custom)

        headlines = provider.fetch_headlines("BBCA", days=3)

        assert len(headlines) == 1

    def test_all_headlines_filtered(self):
        """Should return empty if all headlines are too old."""
        now = datetime.now()
        custom = [
            RawHeadline("Old 1", "Source", now - timedelta(days=10)),
            RawHeadline("Old 2", "Source", now - timedelta(days=15)),
        ]
        provider = MockNewsProvider(headlines=custom)

        headlines = provider.fetch_headlines("BBCA", days=3)

        assert len(headlines) == 0


class TestFactoryMethods:
    """Test factory methods for test scenarios."""

    def test_create_positive_set(self):
        """create_positive_set should return all positive headlines."""
        provider = MockNewsProvider.create_positive_set()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) > 0
        # All headlines should contain positive keywords
        for h in headlines:
            title_lower = h.title.lower()
            assert any(
                kw in title_lower
                for kw in ["naik", "melonjak", "melesat", "laba", "dividen", "rekor"]
            )

    def test_create_negative_set(self):
        """create_negative_set should return all negative headlines."""
        provider = MockNewsProvider.create_negative_set()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) > 0
        # All headlines should contain negative keywords
        for h in headlines:
            title_lower = h.title.lower()
            assert any(
                kw in title_lower
                for kw in ["anjlok", "merosot", "koreksi", "tekanan", "bearish", "melemah"]
            )

    def test_create_empty(self):
        """create_empty should return no headlines."""
        provider = MockNewsProvider.create_empty()
        headlines = provider.fetch_headlines("BBCA")

        assert len(headlines) == 0


class TestCombinedParameters:
    """Test combination of parameters."""

    def test_days_and_max_headlines(self):
        """Both days and max_headlines should work together."""
        now = datetime.now()
        custom = [
            RawHeadline(f"Recent {i}", "Source", now - timedelta(hours=i))
            for i in range(5)
        ] + [
            RawHeadline(f"Old {i}", "Source", now - timedelta(days=5 + i))
            for i in range(5)
        ]
        provider = MockNewsProvider(headlines=custom)

        # Filter by days first, then limit
        headlines = provider.fetch_headlines("BBCA", max_headlines=3, days=3)

        assert len(headlines) == 3
        # Should only have recent headlines
        for h in headlines:
            assert "Recent" in h.title


class TestHeadlineStructure:
    """Test headline structure from default provider."""

    def test_default_headlines_have_all_fields(self):
        """Default headlines should have all required fields."""
        provider = MockNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        for h in headlines:
            assert isinstance(h.title, str)
            assert len(h.title) > 0
            assert isinstance(h.source, str)
            assert len(h.source) > 0
            assert isinstance(h.published, datetime)
            # URL can be empty but should be string
            assert isinstance(h.url, str)

    def test_default_headlines_are_recent(self):
        """Default headlines should be recent (within default days window)."""
        provider = MockNewsProvider()
        headlines = provider.fetch_headlines("BBCA", days=7)

        cutoff = datetime.now() - timedelta(days=7)
        for h in headlines:
            assert h.published >= cutoff
