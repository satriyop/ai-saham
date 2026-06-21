"""
StockbitRunningTradeProvider — fetch live executed trade ticks from Stockbit.

Calls /order-trade/running-trade?symbols[]={ticker}&sort=DESC&limit={limit}&order_by=RUNNING_TRADE_ORDER_BY_TIME
and returns parsed TradeTick objects (newest first).

No cache: running trade data changes every second — caching would be stale immediately.
Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), RunningTradeProvider port
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.domain.entities.trade_tick import TradeTick
from src.domain.ports.running_trade_provider import RunningTradeProvider

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG
_RUNNING_TRADE_URL = STOCKBIT_CFG.running_trade_url


def _parse_ticks(ticker: str, body: dict) -> list[TradeTick]:
    """Parse running-trade response into TradeTick list.

    Actual Stockbit Exodus response shape (confirmed 2026-06):
      data.running_trade[] — list of trade tick objects, each with:
        time          → "HH:MM:SS" (time only — combined with today's IDX date)
        price         → "6,400"   (string with thousand-separator commas)
        lot           → "0.98"    (string, may be fractional for odd-lot / NG board)
        code          → "BBCA"    (ticker symbol)
        buyer         → ""        (empty when is_broker_exists=false)
        seller        → ""
        buyer_type    → "BROKER_TYPE_UNSPECIFIED" or broker code
        seller_type   → broker code
        is_broker_exists → bool
        market_board  → "RG" (regular) | "NG" (negotiated) | "TN" (tunai)
        value.raw     → int, IDR value of the trade
    """
    from src.domain.value_objects.idx_market import IDX_TIMEZONE as IDX_TZ
    today = datetime.now(IDX_TZ).date()

    data = body.get("data") if isinstance(body, dict) else None
    if data is None:
        return []

    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("running_trade", "list", "trades", "items"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                items = candidate
                break

    ticks: list[TradeTick] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        # Timestamp — Stockbit returns "HH:MM:SS", combine with today's date
        raw_ts = (
            item.get("time")
            or item.get("created_at")
            or item.get("timestamp")
            or item.get("trade_time")
        )
        try:
            if isinstance(raw_ts, (int, float)):
                ts = datetime.fromtimestamp(raw_ts, tz=IDX_TZ)
            elif raw_ts and len(str(raw_ts)) <= 8:
                # "HH:MM:SS" — attach today's date in IDX timezone
                from datetime import time as dt_time
                t = dt_time.fromisoformat(str(raw_ts))
                ts = datetime(today.year, today.month, today.day,
                              t.hour, t.minute, t.second, tzinfo=IDX_TZ)
            else:
                ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            ts = datetime.now(tz=IDX_TZ)

        # Price — may be "6,400" (comma-formatted string)
        raw_price = item.get("price") or item.get("last_price") or item.get("trade_price")
        try:
            price = float(str(raw_price).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue

        # Lot — may be fractional string "0.98" (odd-lot or negotiated board)
        raw_lot = item.get("lot") or item.get("volume") or item.get("qty") or item.get("lots")
        try:
            lot = max(1, round(float(str(raw_lot).replace(",", ""))))
        except (TypeError, ValueError):
            continue

        # Broker codes — empty string when is_broker_exists=false (NG/negotiated trades)
        buyer = str(item.get("buyer") or item.get("buyer_code") or "").upper().strip()
        seller = str(item.get("seller") or item.get("seller_code") or "").upper().strip()

        # Fallback: some responses put broker codes in buyer_type/seller_type
        if not buyer:
            bt = str(item.get("buyer_type") or "")
            if bt and "UNSPECIFIED" not in bt and "TYPE" not in bt:
                buyer = bt.upper().strip()
        if not seller:
            st = str(item.get("seller_type") or "")
            if st and "UNSPECIFIED" not in st and "TYPE" not in st:
                seller = st.upper().strip()

        trade_type = str(item.get("trade_type") or item.get("action") or item.get("market_board") or "").strip()
        investor_type = str(
            item.get("investor_type") or item.get("type_investor") or item.get("inv_type") or ""
        ).strip().upper()

        ticks.append(TradeTick(
            ticker=ticker.upper(),
            timestamp=ts,
            price=price,
            lot=lot,
            buyer_broker_code=buyer,
            seller_broker_code=seller,
            trade_type=trade_type,
            investor_type=investor_type,
        ))

    return ticks


class StockbitRunningTradeProvider(RunningTradeProvider):
    """Fetches live running-trade ticks from Stockbit Exodus API.

    No in-memory cache — tick data is real-time and changes every second.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider

    def fetch_running_trade(self, ticker: str, limit: int = 80) -> list[TradeTick]:
        """Return the most recent executed ticks for ticker. Returns [] on any error."""
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _RUNNING_TRADE_URL.format(ticker=ticker.upper(), limit=limit)
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty running-trade response for %s", ticker)
                return []
            ticks = _parse_ticks(ticker, body)
            logger.debug("Running trade %s → %d ticks", ticker, len(ticks))
            return ticks
        except Exception as e:
            logger.warning("Running trade fetch failed for %s: %s", ticker, e)
            return []
