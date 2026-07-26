"""
Pre-open candidate builder — pure assembly of ScreenerCandidate from pre-computed values.

Layer: Application
"""

from decimal import Decimal

from src.domain.value_objects.screener_result import (
    MoverData,
    ScreenerCandidate,
    TickerNotationSnapshot,
)


def build_pre_open_candidate(
    ticker: str,
    mover: MoverData,
    entry_price: Decimal | None,
    stop_loss_price: Decimal | None,
    capital: Decimal,
    trend_signal: str | None,
    rsi: Decimal | None,
    sma: Decimal | None,
    ai_summary: str | None,
    atr: Decimal | None,
    prev_close: Decimal | None,
    prev_high: Decimal | None,
    prev_low: Decimal | None,
    gap_pct: Decimal | None,
    iep_gap_pct: Decimal | None,
    best_bid: Decimal | None,
    bid_gap_pct: Decimal | None,
    gap_price_source: str | None,
    entry_range_low: Decimal | None,
    entry_range_high: Decimal | None,
    opening_broker_backing_score: float | None,
    opening_broker_backing_tag: str | None,
    opening_broker_buy_streak: int | None,
    foreign_vwap: Decimal | None,
    fvwap_discount_pct: float | None,
    iev_intensity: float | None,
    unusual_volume: bool,
    best_offer: Decimal | None,
    best_offer_lots: int | None,
    spread_pct: Decimal | None,
    bid_offer_imbalance: float | None,
    ticker_notation: TickerNotationSnapshot | None,
) -> ScreenerCandidate:
    """Assemble a ScreenerCandidate from pre-computed values.

    Pure assembly only — no I/O, no computation, no config access.
    """
    return ScreenerCandidate(
        ticker=ticker,
        iev=mover.iev,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        capital=capital,
        trend_signal=trend_signal,
        rsi=rsi,
        sma=sma,
        ai_summary=ai_summary,
        atr=atr,
        prev_close=prev_close,
        prev_high=prev_high,
        prev_low=prev_low,
        gap_pct=gap_pct,
        iep=mover.iep,
        iep_gap_pct=iep_gap_pct,
        best_bid=best_bid,
        bid_gap_pct=bid_gap_pct,
        gap_price_source=gap_price_source,
        entry_range_low=entry_range_low,
        entry_range_high=entry_range_high,
        opening_broker_backing_score=opening_broker_backing_score,
        opening_broker_backing_tag=opening_broker_backing_tag,
        opening_broker_buy_streak=opening_broker_buy_streak,
        foreign_vwap=foreign_vwap,
        fvwap_discount_pct=fvwap_discount_pct,
        iev_intensity=iev_intensity,
        unusual_volume=unusual_volume,
        best_offer=best_offer,
        best_offer_lots=best_offer_lots,
        spread_pct=spread_pct,
        bid_offer_imbalance=bid_offer_imbalance,
        ticker_notation=ticker_notation,
    )
