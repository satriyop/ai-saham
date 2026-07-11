"""
Pre-open order book derived context: bid gap%, spread%, imbalance, gap band warnings.

Layer: Application
"""

from dataclasses import dataclass
from decimal import Decimal

from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import MoverData


@dataclass(frozen=True)
class PreOpenOrderBookContext:
    """Derived order-book context for a pre-open ticker.

    Attributes:
        bid_price: Best bid price from order book (None if unavailable)
        gap_pct: (bid - prev_close) / prev_close * 100; IEP fallback if no bid
        spread_pct: (offer - bid) / bid * 100 (None if no offer side)
        bid_offer_imbalance: bid_lots / (bid_lots + offer_lots) (None without offer)
        warnings: Gap-band or missing-data warning strings for the use case
        best_offer: Best offer price (None if unavailable)
        best_offer_lots: Lots queued at best offer (None if unavailable)
    """

    bid_price: Decimal | None = None
    gap_pct: Decimal | None = None
    spread_pct: Decimal | None = None
    bid_offer_imbalance: float | None = None
    warnings: tuple[str, ...] = ()
    best_offer: Decimal | None = None
    best_offer_lots: int | None = None


def build_pre_open_order_book_context(
    browser: BrowserDataProvider,
    ticker: str,
    mover: MoverData,
    prev_close: Decimal | None,
    effective_band: Decimal,
    fast_mode: bool,
) -> PreOpenOrderBookContext:
    """Fetch order-book top-of-book and compute derived metrics.

    Skipped in fast_mode — returns default context (all None, no warnings).
    """
    if fast_mode:
        return PreOpenOrderBookContext()

    tob = browser.fetch_order_book_top_of_book(ticker)
    ob = tob.bid if tob else None

    if ob is not None:
        gap_pct: Decimal | None = None
        spread_pct: Decimal | None = None
        bid_offer_imbalance: float | None = None
        warnings: list[str] = []

        if prev_close is not None and prev_close > 0:
            gap_pct = ((ob.price - prev_close) / prev_close * 100).quantize(Decimal("0.01"))
            if abs(gap_pct) > effective_band * 100:
                warnings.append(
                    f"{ticker}: Gap {gap_pct:+.1f}% exceeds "
                    f"±{float(effective_band * 100):.1f}% ATR band"
                )

        best_offer: Decimal | None = None
        best_offer_lots: int | None = None
        if tob and tob.offer:
            best_offer = tob.offer.price
            best_offer_lots = tob.offer.volume
            spread_pct = ((tob.offer.price - ob.price) / ob.price * 100).quantize(Decimal("0.01"))
            total_lots = ob.volume + tob.offer.volume
            if total_lots > 0:
                bid_offer_imbalance = round(ob.volume / total_lots, 3)

        return PreOpenOrderBookContext(
            bid_price=ob.price,
            gap_pct=gap_pct,
            spread_pct=spread_pct,
            bid_offer_imbalance=bid_offer_imbalance,
            warnings=tuple(warnings),
            best_offer=best_offer,
            best_offer_lots=best_offer_lots,
        )

    # No order book bid — IEP fallback or no-data
    if mover.iep is not None and prev_close is not None and prev_close > 0:
        gap_pct = ((Decimal(mover.iep) - prev_close) / prev_close * 100).quantize(Decimal("0.01"))
        return PreOpenOrderBookContext(
            gap_pct=gap_pct,
            warnings=(f"{ticker}: No order book bid — gap% from IEP ({mover.iep})",),
        )

    return PreOpenOrderBookContext(
        warnings=(f"{ticker}: No order book data — gap% not computed",),
    )
