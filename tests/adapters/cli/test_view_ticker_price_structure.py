"""Unit tests for ticker dashboard price-structure helpers."""

from datetime import date, timedelta
from decimal import Decimal

from src.adapters.cli.view_ticker_price_structure import (
    compute_price_structure,
    price_structure_to_dict,
)
from src.domain.entities.candle import Candle


def _candle(day: int, close: str, *, volume: int = 1_000_000, high=None, low=None) -> Candle:
    c = Decimal(close)
    return Candle(
        ticker="BBCA",
        date=date(2026, 7, 1) + timedelta(days=day),
        open=c,
        high=high if high is not None else c + Decimal("50"),
        low=low if low is not None else c - Decimal("50"),
        close=c,
        volume=volume,
    )


def test_compute_price_structure_changes_range_and_volume():
    candles = [_candle(i, str(1000 + i * 10), volume=1_000_000 + i * 10_000) for i in range(25)]
    # Make latest volume 2x average-ish
    candles[-1] = _candle(24, "1240", volume=3_000_000)

    structure = compute_price_structure(
        candles,
        week52_high=Decimal("1500"),
        week52_low=Decimal("1000"),
    )

    assert structure is not None
    assert structure.close == Decimal("1240")
    assert structure.change_1d_pct is not None
    assert structure.change_5d_pct is not None
    assert structure.change_20d_pct is not None
    # 1d: 1240 vs 1230
    assert abs(structure.change_1d_pct - ((1240 - 1230) / 1230 * 100)) < 1e-6
    assert structure.range_52w_pct is not None
    assert abs(structure.range_52w_pct - 48.0) < 1e-6  # (1240-1000)/(1500-1000)
    assert structure.volume_vs_20d is not None
    assert structure.volume_vs_20d > 1.0

    payload = price_structure_to_dict(structure)
    assert payload["close"] == "1240"
    assert payload["as_of"] == structure.as_of.isoformat()


def test_compute_price_structure_returns_none_without_candles():
    assert compute_price_structure([]) is None
    assert price_structure_to_dict(None) is None
