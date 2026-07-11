"""
Pre-open entry plan: ATR-scaled entry range, entry price, stop-loss, trend classification.

Layer: Application
"""

from decimal import Decimal

from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.domain.value_objects.tick_size import (
    entry_price_from_bid,
    suggested_limit_from_close,
)


def compute_pre_open_entry_range(
    prev_close: Decimal | None,
    atr: Decimal | None,
    config: PreOpenScreenConfig,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    """Compute effective gap band and entry range.

    Improvement #3: use ATR-scaled band (ATR/prev_close) instead of fixed %.
    Returns (effective_band, range_low, range_high).
    """
    if config.use_atr_range and atr is not None and prev_close is not None and prev_close > 0:
        atr_pct = atr / prev_close
        effective_band = max(
            config.atr_range_cap_min,
            min(atr_pct, config.atr_range_cap_max),
        )
    else:
        effective_band = config.max_gap_pct

    if prev_close is None or prev_close <= 0:
        return effective_band, None, None

    low = (prev_close * (1 - effective_band)).quantize(Decimal("1"))
    high = (prev_close * (1 + effective_band)).quantize(Decimal("1"))
    return effective_band, low, high


def compute_pre_open_entry_price(
    prev_close: Decimal | None,
    bid_price: Decimal | None,
    config: PreOpenScreenConfig,
) -> Decimal | None:
    """Compute suggested entry price.

    In fast mode (no order book), uses suggested_limit_from_close.
    Falls back to entry_price_from_bid when only bid is available.
    Returns None if neither prev_close nor bid_price is available.
    """
    if prev_close is not None and prev_close > 0:
        return suggested_limit_from_close(prev_close, config.suggested_limit_pct)
    if bid_price is not None:
        return entry_price_from_bid(bid_price, config.tick_above)
    return None


def compute_pre_open_stop_loss(
    entry_price: Decimal | None,
    atr: Decimal | None,
    config: PreOpenScreenConfig,
) -> Decimal | None:
    """Compute ATR-based stop-loss (or legacy fixed-pct fallback).

    Returns None when entry_price is None (caller decides skip flow).
    """
    if entry_price is None:
        return None

    if config.use_atr_stop and atr is not None:
        raw_stop = entry_price - (config.atr_multiplier * atr)
        floor_stop = entry_price * (1 - config.max_stop_pct)
        return max(raw_stop, floor_stop, Decimal("50")).quantize(Decimal("1"))

    return max(entry_price * (1 - config.stop_loss_pct), Decimal("50")).quantize(Decimal("1"))


def classify_pre_open_trend(
    gap_pct: Decimal | None,
    rsi: Decimal | None,
    effective_band: Decimal,
    rsi_overbought: Decimal,
    close: Decimal | None = None,
    sma: Decimal | None = None,
) -> str | None:
    """Classify trend using gap% (vs effective ATR band) and RSI gate."""
    if rsi is not None and rsi > rsi_overbought:
        return "BEARISH"

    if gap_pct is not None and abs(gap_pct) > effective_band * 100:
        return "GAP_OUT"

    if rsi is not None and Decimal("30") < rsi < Decimal("65"):
        if gap_pct is not None and abs(gap_pct) <= Decimal("2"):
            return "BULLISH"

    if gap_pct is None and close is not None and sma is not None:
        return _classify_trend_legacy(close, sma, rsi)

    return "NEUTRAL"


def _classify_trend_legacy(
    close: Decimal | None,
    sma: Decimal | None,
    rsi: Decimal | None,
) -> str | None:
    """Original SMA-based trend classifier (fallback for fast mode)."""
    if close is None or sma is None or rsi is None:
        return None
    above_sma = close > sma
    overbought = rsi > Decimal("65")
    if above_sma and not overbought:
        return "BULLISH"
    if not above_sma and overbought:
        return "BEARISH"
    if above_sma and rsi < Decimal("40"):
        return "DIP_BUY"
    return "NEUTRAL"
