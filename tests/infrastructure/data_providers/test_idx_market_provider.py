from datetime import date
from decimal import Decimal

from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider


def test_idx_market_provider_exposes_candle_provenance_metadata() -> None:
    provider = IdxMarketDataProvider()

    assert provider.provider_name == "idx"
    assert provider.volume_unit == "shares"
    assert provider.price_adjustment_policy == "raw"


def test_idx_market_provider_keeps_volume_in_shares() -> None:
    provider = IdxMarketDataProvider()

    candle = provider._parse_candle(
        {
            "Date": "2026-06-18T00:00:00",
            "OpenPrice": 1000,
            "High": 1100,
            "Low": 900,
            "Close": 1050,
            "Volume": 12345600,
        },
        "BBCA",
    )

    assert candle.ticker == "BBCA"
    assert candle.date == date(2026, 6, 18)
    assert candle.open == Decimal("1000")
    assert candle.volume == 12345600
