from datetime import date
from decimal import Decimal

from src.application.services.market_context_quality_warnings import (
    market_context_staleness_warning,
)
from src.domain.entities.candle import Candle


def test_staleness_warning_contains_actionable_universe_flag():
    as_of = date(2026, 7, 9)
    stale_date = date(2026, 7, 6)

    vix_candles = [
        Candle(
            ticker="^VIX",
            date=stale_date,
            open=Decimal("15"),
            high=Decimal("15"),
            low=Decimal("15"),
            close=Decimal("15"),
            volume=100,
        )
    ]
    eido_candles = [
        Candle(
            ticker="EIDO",
            date=stale_date,
            open=Decimal("20"),
            high=Decimal("20"),
            low=Decimal("20"),
            close=Decimal("20"),
            volume=100,
        )
    ]
    usd_idr_candles = [
        Candle(
            ticker="IDR=X",
            date=stale_date,
            open=Decimal("15000"),
            high=Decimal("15000"),
            low=Decimal("15000"),
            close=Decimal("15000"),
            volume=100,
        )
    ]

    warning = market_context_staleness_warning(
        vix_candles=vix_candles,
        eido_candles=eido_candles,
        usd_idr_candles=usd_idr_candles,
        as_of=as_of,
        stale_business_day_gap=1,
    )

    assert warning is not None
    assert "Run: saham fetch market --universe lq45" in warning
