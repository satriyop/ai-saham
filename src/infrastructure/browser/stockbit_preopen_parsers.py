"""
Pure parsers for Stockbit IEV/orderbook/mover JSON payloads.

Extracted from playwright_stockbit_provider.py. These functions do no network,
browser, DB, or token-store I/O — they only transform already-fetched response
bodies into domain value objects.

Layer: Infrastructure
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from src.domain.value_objects.screener_result import (
    MoverData,
    OrderBookBid,
    OrderBookTopOfBook,
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
            ticker = _extract_ticker(item)
            iev = _extract_iev_from_mover(item)
            iep = _extract_iep_from_mover(item)
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev, iep=iep))

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def _extract_ticker_confirmed(item: dict) -> str | None:
    """Extract ticker from confirmed Exodus mover_list item shape."""
    code = (item.get("stock_detail") or {}).get("code")
    if isinstance(code, str) and 2 <= len(code) <= 6:
        return code.upper()
    return _extract_ticker(item)  # fallback


def _extract_iev_confirmed(item: dict) -> int | None:
    """Extract IEV from confirmed Exodus mover_list item shape."""
    raw = (item.get("iepiev_detail") or {}).get("iev", {}).get("raw")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return _extract_iev_from_mover(item)  # fallback


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


def _extract_iep_from_mover(item: dict) -> int | None:
    """Extract IEP value from generic mover payloads."""
    for key in ("iep", "IEP", "indicative_equilibrium_price", "equilibrium_price"):
        val = item.get(key)
        if val is not None:
            try:
                return int(float(str(val).replace(",", "")))
            except (ValueError, TypeError):
                pass
    for nested_key in ("stock", "data", "detail", "iepiev_detail"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            result = _extract_iep_from_mover(nested)
            if result is not None:
                return result
    return None


def _extract_iev_from_mover(item: dict) -> int | None:
    """Extract IEV value — generic fallback for unknown response shapes."""
    for key in ("iev", "IEV", "intraday_expected_volume", "ie_volume",
                "expected_volume", "volume_iev"):
        val = item.get(key)
        if val is not None:
            try:
                return int(float(str(val).replace("K", "e3").replace("M", "e6")))
            except (ValueError, TypeError):
                pass
    for nested_key in ("stock", "data", "detail", "iepiev_detail"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            result = _extract_iev_from_mover(nested)
            if result is not None:
                return result
    return None


def _parse_order_book_response(body: dict) -> OrderBookTopOfBook | None:
    """
    Parse order book API response from Exodus.
    Uses confirmed company-price-feed/v2/orderbook response shape.
    Returns both bid and offer sides.
    """
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    bid = OrderBookBid(price=bid_price, volume=bid_lots) if bid_price and bid_lots else None
    offer = OrderBookBid(price=offer_price, volume=offer_lots) if offer_price and offer_lots else None
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


def _find_side_list(obj: Any, keys: tuple[str, ...], depth: int = 0) -> list | None:
    """Recursively search for a named list (bid side or offer side) in JSON."""
    if depth > 5 or not isinstance(obj, dict):
        return None
    for key in keys:
        val = obj.get(key) or obj.get(key.upper())
        if isinstance(val, list) and val:
            return val
    for v in obj.values():
        result = _find_side_list(v, keys, depth + 1)
        if result:
            return result
    return None


def _parse_movers_from_api(
    responses: list[dict], iev_min: int
) -> list[MoverData]:
    """
    Attempt to extract MoverData from captured API responses.

    Tries common response shapes. Run `saham fetch stockbit spy` to see the
    actual shape and update this function accordingly.
    """
    movers: list[MoverData] = []

    for resp in responses:
        body = resp.get("body")
        if not isinstance(body, dict):
            continue

        # Try to find a list field that looks like movers
        candidates = _find_list_in_json(body)
        for item_list in candidates:
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                ticker = _extract_ticker(item)
                iev = _extract_iev(item)
                if ticker and iev is not None and iev >= iev_min:
                    movers.append(MoverData(ticker=ticker, iev=iev))

        if movers:
            break

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def _parse_best_bid_from_api(
    responses: list[dict], ticker: str
) -> OrderBookBid | None:
    """
    Attempt to extract best bid from captured order book API responses.

    Tries common response shapes. Run `saham fetch stockbit spy` to see the
    actual shape and update this function accordingly.
    """
    for resp in responses:
        body = resp.get("body")
        if not isinstance(body, dict):
            continue

        bid = _find_best_bid_in_json(body)
        if bid:
            return bid

    return None


def _find_list_in_json(obj: Any, depth: int = 0) -> list[list]:
    """Recursively find all list values in a JSON object."""
    if depth > 4:
        return []
    results = []
    if isinstance(obj, list) and len(obj) > 0:
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_find_list_in_json(v, depth + 1))
    return results


def _extract_ticker(item: dict) -> str | None:
    """Try common field names for ticker symbol."""
    for key in ("symbol", "ticker", "stock_code", "kode", "code", "emiten"):
        val = item.get(key) or item.get(key.upper())
        if isinstance(val, str) and 2 <= len(val) <= 6:
            return val.upper()
    return None


def _extract_iev(item: dict) -> int | None:
    """Try common field names for IEV."""
    for key in ("iev", "IEV", "intraday_expected_volume", "expected_volume",
                "pre_open_volume", "volume_expected"):
        val = item.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None


def _find_best_bid_in_json(obj: Any, depth: int = 0) -> OrderBookBid | None:
    """Recursively search for bid data in an order book response."""
    if depth > 5:
        return None

    if isinstance(obj, dict):
        # Look for a "bid" key containing a list
        for key in ("bid", "buy", "bids", "buys", "buyer"):
            val = obj.get(key) or obj.get(key.upper())
            if isinstance(val, list) and val:
                best = _best_bid_from_list(val)
                if best:
                    return best

        # Recurse
        for v in obj.values():
            result = _find_best_bid_in_json(v, depth + 1)
            if result:
                return result

    elif isinstance(obj, list):
        best = _best_bid_from_list(obj)
        if best:
            return best

    return None


def _best_bid_from_list(items: list) -> OrderBookBid | None:
    """Find the bid entry with the largest volume from a list of dicts."""
    best_price: Decimal | None = None
    best_volume: int = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        price = _extract_price(item)
        volume = _extract_volume(item)
        if price is not None and volume is not None and volume > best_volume:
            best_price = price
            best_volume = volume

    if best_price is not None and best_volume > 0:
        return OrderBookBid(price=best_price, volume=best_volume)
    return None


def _extract_price(item: dict) -> Decimal | None:
    for key in ("price", "harga", "last_price", "bid_price", "p"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return Decimal(str(val))
            except (InvalidOperation, TypeError):
                pass
    return None


def _extract_volume(item: dict) -> int | None:
    # Stockbit orderbook uses "lot" as the column name (visible in UI)
    for key in ("lot", "lots", "volume", "qty", "quantity", "vol", "v"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None
