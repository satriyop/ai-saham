"""
StockbitOrderBookProvider — full order book from Stockbit Exodus API.

Calls /company-price-feed/v2/orderbook/companies/{ticker} and returns an
OrderBookSnapshot with aggregate bid/offer depth, live foreign flow, and IEP/IEV.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.bid[]           → [{price, que_num, volume, change_percentage}, ...]  (bid side)
  data.offer[]         → same shape (offer/ask side)
  data.total_bid_offer → {bid: {freq, lot}, offer: {freq, lot}}  (totals, comma strings)
  data.lastprice       → int  (last traded price)
  data.fnet            → int  (running foreign net IDR today)
  data.fbuy            → int  (running foreign buy IDR today)
  data.fsell           → int  (running foreign sell IDR today)
  data.foreign         → str  (e.g. "78.11" — % of daily value from foreign investors)
  data.domestic        → str  (e.g. "21.89")
  data.ara             → {"value": "7,550", "visible": true}  (auto-reject ceiling)
  data.arb             → {"value": "5,375", "visible": true}  (auto-reject floor)
  data.iepiev.iep.raw  → int  (IEP, 0 during regular session)
  data.iepiev.iev.raw  → int  (IEV lots, 0 during regular session)
  data.iepiev.best_bid_offer.bid.price.raw   → int  (best bid price)
  data.iepiev.best_bid_offer.offer.price.raw → int  (best offer price)

No caching — order book is real-time data that must be fresh on each call.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.ports.order_book_provider import OrderBookProvider
from src.domain.value_objects.order_book_snapshot import OrderBookSnapshot
from src.infrastructure.config.stockbit_config import (
    StockbitConfig,
    load_stockbit_config,
)

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

_DEPTH_LEVELS = 5  # top N levels for depth_ratio computation


def _parse_lots(raw: str | int | None) -> int:
    """Parse lot string like '49,960,400' to int."""
    if raw is None:
        return 0
    try:
        return int(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _parse_float(raw) -> float:
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _depth_volume(levels: list[dict], n: int) -> int:
    """Sum of volume across top N levels (levels already ordered closest-to-mid first)."""
    total = 0
    for lvl in levels[:n]:
        total += _parse_lots(lvl.get("volume"))
    return total


def _parse_snapshot(ticker: str, body: dict) -> OrderBookSnapshot | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    bid_levels = data.get("bid") or []
    offer_levels = data.get("offer") or []

    # Best bid/offer — top-of-book
    best_bid = _parse_float(bid_levels[0].get("price") if bid_levels else 0)
    best_offer = _parse_float(offer_levels[0].get("price") if offer_levels else 0)
    last_price = float(data.get("lastprice") or data.get("close") or 0)
    if last_price == 0 and best_bid:
        last_price = best_bid

    # Aggregate depth totals
    tbo = data.get("total_bid_offer") or {}
    total_bid_lots = _parse_lots((tbo.get("bid") or {}).get("lot"))
    total_offer_lots = _parse_lots((tbo.get("offer") or {}).get("lot"))

    # Top-5 depth (bid = descending price = closest to last price first)
    bid_depth_5 = _depth_volume(bid_levels, _DEPTH_LEVELS)
    offer_depth_5 = _depth_volume(offer_levels, _DEPTH_LEVELS)

    # Live foreign flow totals
    fnet = float(data.get("fnet") or 0) or None
    fbuy = float(data.get("fbuy") or 0) or None
    fsell = float(data.get("fsell") or 0) or None

    # Foreign/domestic % split and ARA/ARB limits (same call, previously ignored)
    foreign_pct = _parse_float(data.get("foreign")) or None
    domestic_pct = _parse_float(data.get("domestic")) or None
    ara_price = _parse_float((data.get("ara") or {}).get("value")) or None
    arb_price = _parse_float((data.get("arb") or {}).get("value")) or None

    # IEP/IEV — non-zero only during pre-open session
    iepiev = data.get("iepiev") or {}
    iep_raw = (iepiev.get("iep") or {}).get("raw") or 0
    iev_raw = (iepiev.get("iev") or {}).get("raw") or 0
    iep = float(iep_raw) if iep_raw else None
    iev = int(iev_raw) if iev_raw else None

    # Prefer iepiev best_bid_offer over raw bid/offer list if populated
    bbo = iepiev.get("best_bid_offer") or {}
    if bbo:
        bbo_bid = (bbo.get("bid") or {}).get("price") or {}
        bbo_offer = (bbo.get("offer") or {}).get("price") or {}
        bbo_bid_price = float(bbo_bid.get("raw") or 0)
        bbo_offer_price = float(bbo_offer.get("raw") or 0)
        if bbo_bid_price:
            best_bid = bbo_bid_price
        if bbo_offer_price:
            best_offer = bbo_offer_price

    if best_bid == 0 and best_offer == 0:
        return None

    return OrderBookSnapshot(
        ticker=ticker.upper(),
        captured_at=datetime.now(),
        last_price=last_price,
        best_bid_price=best_bid,
        best_offer_price=best_offer,
        total_bid_lots=total_bid_lots,
        total_offer_lots=total_offer_lots,
        bid_depth_5=bid_depth_5,
        offer_depth_5=offer_depth_5,
        fnet_intraday=fnet,
        fbuy_intraday=fbuy,
        fsell_intraday=fsell,
        iep=iep,
        iev=iev,
        ara_price=ara_price,
        arb_price=arb_price,
        foreign_pct=foreign_pct,
        domestic_pct=domestic_pct,
    )


class StockbitOrderBookProvider(OrderBookProvider):
    """Fetches full order book snapshot from Stockbit Exodus API.

    No cache — order book is real-time; each call fetches fresh data.
    """

    def __init__(
        self, api_client: "StockbitApiClient | None", stockbit_config: StockbitConfig | None = None
    ) -> None:
        self._api_client = api_client
        self._stockbit_config = stockbit_config or load_stockbit_config()

    def fetch_snapshot(self, ticker: str) -> OrderBookSnapshot | None:
        try:
            url = self._stockbit_config.orderbook_url.format(ticker=ticker.upper())
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty order book response for %s", ticker)
                return None
            result = _parse_snapshot(ticker, body)
            if result:
                logger.debug(
                    "OrderBook %s → bid_pressure=%.2f fnet=%.1fB",
                    ticker,
                    result.bid_pressure_ratio or 0,
                    (result.fnet_intraday or 0) / 1e9,
                )
            return result
        except Exception as e:
            logger.warning("Order book fetch failed for %s: %s", ticker, e)
            return None
