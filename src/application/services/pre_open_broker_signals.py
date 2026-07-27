"""
Pre-open broker signals: opening broker-backing tag + Foreign VWAP.

Layer: Application
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.application.services.stats import foreign_vwap_discount_pct


@dataclass(frozen=True)
class PreOpenBrokerSignals:
    """Broker-derived signals for a pre-open ticker.

    All fields default to None — consumer checks for None to decide
    whether the signal is available.
    """

    opening_broker_backing_score: float | None = None
    opening_broker_backing_tag: str | None = None
    opening_broker_buy_streak: int | None = None
    foreign_vwap: Decimal | None = None
    fvwap_discount_pct: float | None = None


def assess_pre_open_broker_signals(
    broker_repository,
    *,
    ticker: str,
    candles: list,
    current_price: Decimal | None,
    broker_backing_window: int,
    broker_backing_threshold: float,
    fvwap_period: int,
) -> PreOpenBrokerSignals:
    """Load broker summaries; compute opening broker-backing tag + Foreign VWAP.

    Args:
        broker_repository: BrokerDataRepository instance (or None-compatible duck)
        ticker: IDX ticker symbol
        candles: List of candle objects for FVWAP computation
        current_price: Reference price for FVWAP discount (ob.price if ob else prev_close)
        broker_backing_window: Days to look back for backing streak
        broker_backing_threshold: Minimum score for BACKED tag
        fvwap_period: Period for ForeignVWAPIndicator

    Returns:
        PreOpenBrokerSignals with computed values (all None on failure/missing data)
    """
    try:
        today = date.today()
        start = today - timedelta(days=broker_backing_window + fvwap_period + 10)
        summaries = broker_repository.get_broker_summaries(
            ticker=ticker, start_date=start, end_date=today
        )
    except Exception:
        return PreOpenBrokerSignals()

    if not summaries:
        return PreOpenBrokerSignals()

    # Improvement #1: Opening broker backing
    cutoff = date.today() - timedelta(days=broker_backing_window)
    window = [s for s in summaries if s.date > cutoff]

    score: float | None = None
    tag: str | None = None
    streak: int | None = None

    if window:
        net_buy_days = sum(1 for s in window if s.is_foreign_accumulating)
        total_days = len(window)
        ratio = net_buy_days / total_days if total_days > 0 else 0.0

        streak = 0
        for s in sorted(window, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        score = round(
            ratio * 40.0 + 30.0 * (1.0 - math.exp(-streak / 7.0)),
            1,
        )

        if score >= broker_backing_threshold:
            tag = "BACKED"
        elif ratio < 0.3:
            tag = "DISTRIBUTING"
        else:
            tag = "UNCONFIRMED"

    # Improvement #2: Foreign VWAP
    fvwap: Decimal | None = None
    fvwap_discount: float | None = None

    if candles and current_price is not None and current_price > 0:
        try:
            from plugins.indicators.foreign_vwap import ForeignVWAPIndicator

            indicator = ForeignVWAPIndicator()
            indicator.set_broker_data(summaries)
            vwap_values = indicator.compute(
                candles[-max(len(candles), fvwap_period) :], fvwap_period
            )
            if vwap_values:
                vwap_latest = vwap_values[-1]
                if vwap_latest > 0:
                    fvwap = vwap_latest
                    fvwap_discount = foreign_vwap_discount_pct(
                        fvwap,
                        current_price,
                        precision=2,
                    )
        except Exception:
            pass

    return PreOpenBrokerSignals(
        opening_broker_backing_score=score,
        opening_broker_backing_tag=tag,
        opening_broker_buy_streak=streak,
        foreign_vwap=fvwap,
        fvwap_discount_pct=fvwap_discount,
    )
