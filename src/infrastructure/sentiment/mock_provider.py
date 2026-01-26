"""
Mock news provider for testing.

Provides configurable mock headlines for unit and integration testing.

Layer: Infrastructure
"""

from datetime import datetime, timedelta

from src.domain.ports.news_provider import RawHeadline


class MockNewsProvider:
    """Mock provider for testing.

    Returns configurable headlines without making network requests.
    Useful for unit tests and local development.

    Usage:
        # Default headlines
        provider = MockNewsProvider()
        headlines = provider.fetch_headlines("BBCA")

        # Custom headlines
        custom = [
            RawHeadline("Test headline", "Test Source", datetime.now()),
        ]
        provider = MockNewsProvider(headlines=custom)
    """

    def __init__(self, headlines: list[RawHeadline] | None = None):
        """Initialize mock provider.

        Args:
            headlines: Custom headlines to return. If None, uses defaults.
        """
        self._headlines = headlines if headlines is not None else self._default_headlines()

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return "mock"

    def fetch_headlines(
        self,
        ticker: str,
        max_headlines: int = 20,
        days: int = 3,
    ) -> list[RawHeadline]:
        """Return mock headlines.

        Args:
            ticker: Stock ticker (used for filtering in default headlines)
            max_headlines: Maximum headlines to return
            days: Number of days to look back (used for date filtering)

        Returns:
            List of mock headlines
        """
        cutoff = datetime.now() - timedelta(days=days)
        filtered = [h for h in self._headlines if h.published >= cutoff]
        return filtered[:max_headlines]

    @staticmethod
    def _default_headlines() -> list[RawHeadline]:
        """Generate default mock headlines for testing."""
        now = datetime.now()
        return [
            RawHeadline(
                title="BBCA Catat Laba Bersih Rp 45 Triliun di 2025",
                source="Kontan",
                published=now,
                url="https://kontan.co.id/news/bbca-laba",
            ),
            RawHeadline(
                title="Saham BBCA Naik 2% di Tengah Penguatan IHSG",
                source="Bisnis Indonesia",
                published=now - timedelta(hours=2),
                url="https://bisnis.com/bbca-naik",
            ),
            RawHeadline(
                title="Perbankan Indonesia Hadapi Tantangan di 2026",
                source="CNBC Indonesia",
                published=now - timedelta(hours=5),
                url="https://cnbcindonesia.com/perbankan",
            ),
            RawHeadline(
                title="Tekanan Jual Asing Masih Menekan Sektor Perbankan",
                source="Detik Finance",
                published=now - timedelta(hours=8),
                url="https://detik.com/finance/perbankan",
            ),
            RawHeadline(
                title="Analis Prediksi BBCA Tetap Jadi Favorit Investor",
                source="Investor Daily",
                published=now - timedelta(hours=12),
                url="https://investordaily.com/bbca",
            ),
        ]

    @staticmethod
    def create_positive_set() -> "MockNewsProvider":
        """Create provider with all positive headlines."""
        now = datetime.now()
        return MockNewsProvider(
            headlines=[
                RawHeadline(
                    "Laba BBCA Melonjak 20% YoY",
                    "Kontan",
                    now,
                ),
                RawHeadline(
                    "Saham BBCA Melesat ke Rekor Tertinggi",
                    "Bisnis",
                    now - timedelta(hours=1),
                ),
                RawHeadline(
                    "BBCA Umumkan Dividen Jumbo untuk Pemegang Saham",
                    "CNBC",
                    now - timedelta(hours=2),
                ),
            ]
        )

    @staticmethod
    def create_negative_set() -> "MockNewsProvider":
        """Create provider with all negative headlines."""
        now = datetime.now()
        return MockNewsProvider(
            headlines=[
                RawHeadline(
                    "Saham BBCA Anjlok 5% Akibat Tekanan Jual",
                    "Kontan",
                    now,
                ),
                RawHeadline(
                    "BBCA Merosot Tajam di Tengah Koreksi Pasar",
                    "Bisnis",
                    now - timedelta(hours=1),
                ),
                RawHeadline(
                    "Sektor Perbankan Tertekan Bearish Terus Melemah",
                    "CNBC",
                    now - timedelta(hours=2),
                ),
            ]
        )

    @staticmethod
    def create_empty() -> "MockNewsProvider":
        """Create provider that returns no headlines."""
        return MockNewsProvider(headlines=[])
