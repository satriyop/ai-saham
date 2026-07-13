"""
Confirmed parsers for Stockbit IEV/orderbook/mover JSON payloads.

Extracted from playwright_stockbit_provider.py. These functions do no network,
browser, DB, or token-store I/O — they only transform already-fetched response
bodies into domain value objects.

Only response shapes verified against a known API contract live here. When a
confirmed field is absent, these parsers may fall back to the exploratory
search helpers in stockbit_preopen_json_search.py — see that module for
lower-confidence, best-effort field guessing.

Layer: Infrastructure
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from src.domain.value_objects.screener_result import (
    MoverData,
    OrderBookBid,
    OrderBookTopOfBook,
)
from src.infrastructure.browser.stockbit_preopen_json_search import (
    search_iep_in_mover,
    search_iev_in_mover,
    search_ticker_field,
)


def _parse_number(text: str) -> int | None:
    """Parse a formatted number string like '1.234.567' or '1,234,567'."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def _parse_iev_response(body: dict, iev_min: int) -> list[MoverData]:
    """
    Parse IEV movers from the Exodus market-mover API response.

    Confirmed response shape (2026-06-13):
      data.mover_list[].stock_detail.code       → ticker
      data.mover_list[].iepiev_detail.iev.raw   → IEV as integer
      data.mover_list[].iepiev_detail.iep.raw   → IEP as integer, when present
    """
    movers: list[MoverData] = []

    # Primary path: data.mover_list
    mover_list = (body.get("data") or {}).get("mover_list")
    if isinstance(mover_list, list):
        for item in mover_list:
            if not isinstance(item, dict):
                continue
            ticker = _extract_ticker_confirmed(item)
            iev = _extract_iev_confirmed(item)
            iep = _extract_iep_confirmed(item)
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev, iep=iep))
        if movers:
            return sorted(movers, key=lambda m: m.iev, reverse=True)

    # Fallback: generic traversal (handles API shape changes)
    payload = body
    for key in ("data", "result", "movers", "items"):
        if isinstance(payload, dict) and key in payload:
            candidate = payload[key]
            if isinstance(candidate, list):
                payload = candidate
                break

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            ticker = search_ticker_field(item)
            iev = search_iev_in_mover(item)
            iep = search_iep_in_mover(item)
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev, iep=iep))

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def _extract_ticker_confirmed(item: dict) -> str | None:
    """Extract ticker from confirmed Exodus mover_list item shape."""
    code = (item.get("stock_detail") or {}).get("code")
    if isinstance(code, str) and 2 <= len(code) <= 6:
        return code.upper()
    return search_ticker_field(item)  # fallback


def _extract_iev_confirmed(item: dict) -> int | None:
    """Extract IEV from confirmed Exodus mover_list item shape."""
    raw = (item.get("iepiev_detail") or {}).get("iev", {}).get("raw")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return search_iev_in_mover(item)  # fallback


def _extract_iep_confirmed(item: dict) -> int | None:
    """Try to extract IEP from iepiev_detail.iep.raw (field presence unconfirmed — may be absent).

    IEP = Indicative Equilibrium Price, the expected call-auction clearing price in IDR.
    Returns None gracefully if the field does not exist in the response.
    """
    raw = (item.get("iepiev_detail") or {}).get("iep", {}).get("raw")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return None


def _parse_order_book_response(body: dict) -> OrderBookTopOfBook | None:
    """
    Parse order book API response from Exodus.
    Uses confirmed company-price-feed/v2/orderbook response shape.
    Returns both bid and offer sides.
    """
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    bid = OrderBookBid(price=bid_price, volume=bid_lots) if bid_price and bid_lots else None
    offer = (
        OrderBookBid(price=offer_price, volume=offer_lots)
        if offer_price and offer_lots
        else None
    )
    if bid is None and offer is None:
        return None
    return OrderBookTopOfBook(bid=bid, offer=offer)


def _parse_top_of_book(
    body: dict | None,
) -> tuple[Decimal | None, int | None, Decimal | None, int | None]:
    """
    Extract best bid and best offer from a company-price-feed/v2/orderbook response.

    Returns (bid_price, bid_lots, offer_price, offer_lots).

    Confirmed response shape (2026-06-13):
      data.iepiev.best_bid_offer.bid.price.raw      → best bid price (int)
      data.iepiev.best_bid_offer.bid.quantity.raw   → best bid lots (int, already in lots)
      data.iepiev.best_bid_offer.offer.price.raw    → best offer price (int)
      data.iepiev.best_bid_offer.offer.quantity.raw → best offer lots (int, already in lots)

    The data.bid[] / data.offer[] lists contain full depth (price as string, volume in shares).
    The iepiev.best_bid_offer represents the pre-open equilibrium top-of-book.
    """
    if not body:
        return None, None, None, None

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None, None, None, None

    # Primary: iepiev.best_bid_offer (confirmed, values already in lots)
    bbo = (data.get("iepiev") or {}).get("best_bid_offer") or {}
    bid_raw = (bbo.get("bid") or {})
    offer_raw = (bbo.get("offer") or {})

    bid_price = _safe_decimal((bid_raw.get("price") or {}).get("raw"))
    bid_lots = _safe_int((bid_raw.get("quantity") or {}).get("raw"))
    offer_price = _safe_decimal((offer_raw.get("price") or {}).get("raw"))
    offer_lots = _safe_int((offer_raw.get("quantity") or {}).get("raw"))

    # If iepiev is missing/zero, fall back to data.bid[0] / data.offer[0]
    # Note: volume in bid/offer list is shares; divide by 100 for lots.
    if bid_price is None or bid_price == 0:
        bid_list = data.get("bid") or []
        if bid_list and isinstance(bid_list[0], dict):
            entry = bid_list[0]
            bid_price = _safe_decimal(entry.get("price"))
            shares = _safe_int(entry.get("volume"))
            bid_lots = (shares // 100) if shares else None

    if offer_price is None or offer_price == 0:
        offer_list = data.get("offer") or []
        if offer_list and isinstance(offer_list[0], dict):
            entry = offer_list[0]
            offer_price = _safe_decimal(entry.get("price"))
            shares = _safe_int(entry.get("volume"))
            offer_lots = (shares // 100) if shares else None

    # Fallback 3: NCP call auction — bid/offer lists empty while exchange locks orders.
    # iepiev.iep.raw is the exchange's own clearing price; use it as synthetic bid.
    # Safe: iep.raw is 0 outside NCP, so _safe_decimal rejects it → no effect.
    if bid_price is None or bid_price == 0:
        iep_raw = (data.get("iepiev") or {}).get("iep", {}).get("raw")
        iep_price = _safe_decimal(iep_raw)
        if iep_price:
            bid_price = iep_price

    return bid_price, bid_lots, offer_price, offer_lots


def _safe_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        d = Decimal(str(val))
        return d if d > 0 else None
    except (InvalidOperation, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
