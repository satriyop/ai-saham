"""
Pre-open auction/order-book context with explicit IEP and bid separation.

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
        gap_pct: Canonical auction gap; IEP preferred, best bid fallback
        iep_gap_pct: IEP-relative gap from previous close
        bid_gap_pct: Best-bid-relative gap from previous close
        gap_price_source: IEP or BEST_BID when gap_pct is available
        spread_pct: (offer - bid) / bid * 100 (None if no offer side)
        bid_offer_imbalance: bid_lots / (bid_lots + offer_lots) (None without offer)
        warnings: Gap-band or missing-data warning strings for the use case
        best_offer: Best offer price (None if unavailable)
        best_offer_lots: Lots queued at best offer (None if unavailable)
    """

    bid_price: Decimal | None = None
    gap_pct: Decimal | None = None
    iep_gap_pct: Decimal | None = None
    bid_gap_pct: Decimal | None = None
    gap_price_source: str | None = None
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
    """Build auction gap plus optional top-of-book metrics.

    IEP is the auction-equilibrium authority when present. Best bid remains
    separate microstructure evidence and is only the canonical gap fallback
    when IEP is missing.
    """
    iep_gap_pct = _price_gap_pct(mover.iep, prev_close)
    if fast_mode:
        return PreOpenOrderBookContext(
            gap_pct=iep_gap_pct,
            iep_gap_pct=iep_gap_pct,
            gap_price_source="IEP" if iep_gap_pct is not None else None,
        )

    tob = browser.fetch_order_book_top_of_book(ticker)
    ob = tob.bid if tob else None

    if ob is not None:
        bid_gap_pct = _price_gap_pct(ob.price, prev_close)
        gap_pct = iep_gap_pct if iep_gap_pct is not None else bid_gap_pct
        gap_price_source = (
            "IEP" if iep_gap_pct is not None else ("BEST_BID" if bid_gap_pct is not None else None)
        )
        spread_pct: Decimal | None = None
        bid_offer_imbalance: float | None = None
        warnings: list[str] = []

        if gap_pct is not None:
            if abs(gap_pct) > effective_band * 100:
                warnings.append(
                    f"{ticker}: {gap_price_source} gap {gap_pct:+.1f}% exceeds "
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
            iep_gap_pct=iep_gap_pct,
            bid_gap_pct=bid_gap_pct,
            gap_price_source=gap_price_source,
            spread_pct=spread_pct,
            bid_offer_imbalance=bid_offer_imbalance,
            warnings=tuple(warnings),
            best_offer=best_offer,
            best_offer_lots=best_offer_lots,
        )

    if iep_gap_pct is not None:
        return PreOpenOrderBookContext(
            gap_pct=iep_gap_pct,
            iep_gap_pct=iep_gap_pct,
            gap_price_source="IEP",
            warnings=(f"{ticker}: No order book bid — gap% from IEP ({mover.iep})",),
        )

    return PreOpenOrderBookContext(
        warnings=(f"{ticker}: No order book data — gap% not computed",),
    )


def _price_gap_pct(
    price: int | Decimal | None,
    prev_close: Decimal | None,
) -> Decimal | None:
    if price is None or prev_close is None or prev_close <= 0:
        return None
    return ((Decimal(price) - prev_close) / prev_close * 100).quantize(Decimal("0.01"))
