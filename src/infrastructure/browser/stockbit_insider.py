"""
StockbitInsiderActivityProvider — insider ownership transactions from Stockbit.

Calls /insider/company/majorholder?symbols={ticker}&date_start=...&date_end=...
and returns parsed InsiderTransaction objects (newest first).

Caching: in-memory per (ticker, from_date, to_date) — data changes only when
a new IDX filing arrives, so caching per CLI session is safe.

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), InsiderActivityProvider port
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.value_objects.insider_transaction import InsiderTransaction

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_INSIDER_URL = (
    "https://exodus.stockbit.com/insider/company/majorholder"
    "?symbols={ticker}&date_start={from_date}&date_end={to_date}"
    "&page=1&limit=50&action_type={action_param}&source_type=SOURCE_TYPE_UNSPECIFIED"
)

_ACTION_MAP = {
    "BUY": "ACTION_TYPE_BUY",
    "SELL": "ACTION_TYPE_SELL",
    "ALL": "ACTION_TYPE_UNSPECIFIED",
}

# Map Stockbit badge strings to short role codes
_BADGE_MAP = {
    "SHAREHOLDER_BADGE_DIREKTUR": "DIREKTUR",
    "SHAREHOLDER_BADGE_KOMISARIS": "KOMISARIS",
}


def _parse_date(raw: str) -> date | None:
    """Parse Stockbit's "25 Mar 26" format into a date object."""
    if not raw:
        return None
    for fmt in ("%d %b %y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _strip_num(s: str) -> float:
    """Strip commas and signs from a number string, return float. Returns 0.0 on failure."""
    try:
        return float(str(s).replace(",", "").replace("+", "").replace("-", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse_transactions(ticker: str, body: dict, action_filter: str) -> list[InsiderTransaction]:
    """Parse /insider/company/majorholder response into InsiderTransaction list.

    Actual Stockbit shape (confirmed 2026-06):
      data.movement[] each:
        name              → insider full name
        symbol            → ticker
        date              → "25 Mar 26" (DD Mon YY)
        action_type       → "ACTION_TYPE_BUY" | "ACTION_TYPE_SELL"
        changes.value     → "+147,933" (shares, signed string)
        price_formatted   → "6,982" (price per share, comma-formatted)
        previous.percentage → "0.0002" (ownership % before)
        current.percentage  → "0.0003" (ownership % after)
        badges[]          → ["SHAREHOLDER_BADGE_DIREKTUR"] | ["SHAREHOLDER_BADGE_KOMISARIS"] | []
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return []

    movements = data.get("movement", [])
    if not isinstance(movements, list):
        return []

    results: list[InsiderTransaction] = []
    for item in movements:
        if not isinstance(item, dict):
            continue

        raw_action = str(item.get("action_type") or "")
        if raw_action == "ACTION_TYPE_BUY":
            action = "BUY"
        elif raw_action == "ACTION_TYPE_SELL":
            action = "SELL"
        else:
            continue

        # Apply filter
        if action_filter not in ("ALL", action):
            continue

        txn_date = _parse_date(str(item.get("date") or ""))
        if txn_date is None:
            continue

        # Shares transacted — abs value of changes.value
        raw_shares = item.get("changes", {}).get("value") or item.get("changes", {}).get("formatted_value") or "0"
        shares = int(_strip_num(raw_shares))
        if shares <= 0:
            continue

        # Price per share
        price = _strip_num(item.get("price_formatted") or "0")

        # Ownership percentages
        own_before = _strip_num((item.get("previous") or {}).get("percentage") or "0")
        own_after = _strip_num((item.get("current") or {}).get("percentage") or "0")

        # Role from badges
        badges = item.get("badges") or []
        role = ""
        for badge in badges:
            if badge in _BADGE_MAP:
                role = _BADGE_MAP[badge]
                break

        results.append(InsiderTransaction(
            ticker=ticker.upper(),
            name=str(item.get("name") or "").strip().title(),
            role=role,
            action_type=action,
            shares=shares,
            price=price,
            transaction_date=txn_date,
            ownership_before_pct=own_before,
            ownership_after_pct=own_after,
        ))

    return results


class StockbitInsiderActivityProvider(InsiderActivityProvider):
    """Fetches insider transactions from Stockbit Exodus API.

    In-memory cache keyed by (ticker, from_date, to_date, action_type) —
    IDX filings are static within a CLI session.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider
        self._cache: dict[tuple, list[InsiderTransaction]] = {}

    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
    ) -> list[InsiderTransaction]:
        key = (ticker.upper(), from_date, to_date, action_type)
        if key in self._cache:
            return self._cache[key]
        result = self._fetch(ticker, from_date, to_date, action_type)
        self._cache[key] = result
        return result

    def _fetch(
        self, ticker: str, from_date: date, to_date: date, action_type: str
    ) -> list[InsiderTransaction]:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            action_param = _ACTION_MAP.get(action_type.upper(), "ACTION_TYPE_BUY")
            url = _INSIDER_URL.format(
                ticker=ticker.upper(),
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
                action_param=action_param,
            )
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty insider response for %s", ticker)
                return []
            txns = _parse_transactions(ticker, body, action_type.upper())
            logger.debug("Insider activity %s → %d transactions", ticker, len(txns))
            return txns
        except Exception as e:
            logger.warning("Insider fetch failed for %s: %s", ticker, e)
            return []
