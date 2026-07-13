"""Lightweight regression: StockbitBrokerProvider builds URLs via the extracted helpers."""

from datetime import date

from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG


class _CapturingApiClient:
    """Fake StockbitApiClient that records the requested URL and returns no body."""

    def __init__(self):
        self.captured_urls: list[str] = []

    def get(self, url, params=None):
        self.captured_urls.append(url)
        return None


def test_fetch_broker_summaries_builds_url_via_helpers():
    client = _CapturingApiClient()
    provider = StockbitBrokerProvider(api_client=client)

    provider.fetch_broker_summaries("bbca", date(2026, 6, 12), date(2026, 6, 18))

    assert len(client.captured_urls) == 1
    url = client.captured_urls[0]
    assert url.startswith(STOCKBIT_CFG.marketdetectors_url)
    assert "/BBCA" in url
    assert "period=BROKER_SUMMARY_PERIOD_LAST_7_DAYS" in url
