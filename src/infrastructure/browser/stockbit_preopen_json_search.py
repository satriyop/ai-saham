"""
Exploratory fallback/recursive JSON search helpers for Stockbit pre-open payloads.

These guess at field names when the confirmed response shape (see
stockbit_preopen_parsers.py) is absent. Not verified against a known API
contract — treat with lower confidence than confirmed parsers.

Layer: Infrastructure
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.domain.value_objects.screener_result import MoverData, OrderBookBid


def _find_side_list_in_json(obj: Any, keys: tuple[str, ...], depth: int = 0) -> list | None:
    """Recursively search for a named list (bid side or offer side) in JSON."""
    if depth > 5 or not isinstance(obj, dict):
        return None
    for key in keys:
        val = obj.get(key) or obj.get(key.upper())
        if isinstance(val, list) and val:
            return val
    for v in obj.values():
        result = _find_side_list_in_json(v, keys, depth + 1)
        if result:
            return result
    return None


def search_movers_in_api_responses(
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
        candidates = _find_lists_in_json(body)
        for item_list in candidates:
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                ticker = search_ticker_field(item)
                iev = search_iev_field(item)
                if ticker and iev is not None and iev >= iev_min:
                    movers.append(MoverData(ticker=ticker, iev=iev))

        if movers:
            break

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def search_best_bid_in_api_responses(
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


def _find_lists_in_json(obj: Any, depth: int = 0) -> list[list]:
    """Recursively find all list values in a JSON object."""
    if depth > 4:
        return []
    results = []
    if isinstance(obj, list) and len(obj) > 0:
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_find_lists_in_json(v, depth + 1))
    return results


def search_ticker_field(item: dict) -> str | None:
    """Try common field names for ticker symbol."""
    for key in ("symbol", "ticker", "stock_code", "kode", "code", "emiten"):
        val = item.get(key) or item.get(key.upper())
        if isinstance(val, str) and 2 <= len(val) <= 6:
            return val.upper()
    return None


def search_iev_field(item: dict) -> int | None:
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


def search_iev_in_mover(item: dict) -> int | None:
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
            result = search_iev_in_mover(nested)
            if result is not None:
                return result
    return None


def search_iep_in_mover(item: dict) -> int | None:
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
            result = search_iep_in_mover(nested)
            if result is not None:
                return result
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
        price = _search_price_field(item)
        volume = _search_volume_field(item)
        if price is not None and volume is not None and volume > best_volume:
            best_price = price
            best_volume = volume

    if best_price is not None and best_volume > 0:
        return OrderBookBid(price=best_price, volume=best_volume)
    return None


def _search_price_field(item: dict) -> Decimal | None:
    for key in ("price", "harga", "last_price", "bid_price", "p"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return Decimal(str(val))
            except (InvalidOperation, TypeError):
                pass
    return None


def _search_volume_field(item: dict) -> int | None:
    # Stockbit orderbook uses "lot" as the column name (visible in UI)
    for key in ("lot", "lots", "volume", "qty", "quantity", "vol", "v"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None
