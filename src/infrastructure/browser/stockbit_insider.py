"""
StockbitInsiderActivityProvider — insider ownership transactions from Stockbit.

Calls /insider/company/majorholder?symbols={ticker}&date_start=...&date_end=...
and returns parsed InsiderTransaction objects (newest first).

Caching: delegated to StockbitInsiderCache (SQLite, table: insider_cache).
TTL = calendar day for live mode. Historical replay is point-in-time:
cache-only, limited to rows fetched on or before the requested as-of date.

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), InsiderActivityProvider port
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_insider_cache import StockbitInsiderCache
from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)
from src.infrastructure.config.stockbit_config import (
    StockbitConfig,
    load_stockbit_config,
)

logger = logging.getLogger(__name__)

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
        chg = item.get("changes", {})
        raw_shares = chg.get("value") or chg.get("formatted_value") or "0"
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


class StockbitInsiderActivityProvider(InsiderActivityProvider, StockbitCachingProvider):
    """Fetches insider transactions from Stockbit Exodus API.

    SQLite daily cache (table: insider_cache, TTL = 1 calendar day for live
    mode), owned by StockbitInsiderCache. Transactions are stored per
    (ticker, name, transaction_date, action_type, fetched_date) so historical
    snapshots remain available for point-in-time replay.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
        db_path: Path to the SQLite database (same data.db used by other repos).
    """

    def __init__(
        self,
        api_client,
        db_path: Path | str = Path("data.db"),
        *,
        stockbit_config: StockbitConfig | None = None,
        connection_provider: StockbitSQLiteConnectionProvider | None = None,
    ) -> None:
        self._stockbit_config = stockbit_config or load_stockbit_config()
        self._db_path = Path(db_path).expanduser()
        self._connection_provider = connection_provider or StockbitSQLiteConnectionProvider()
        self._cache = StockbitInsiderCache(self._get_conn())
        super().__init__(
            api_client,
            db_path,
            connection_provider=self._connection_provider,
        )

    def _ensure_schema(self) -> None:
        self._cache.ensure_schema()

    def _is_cache_fresh(self, ticker: str) -> bool:
        return self._cache.is_fresh(ticker)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]:
        """Return insider transactions in [from_date, to_date].

        Live mode checks SQLite cache first (TTL = today), then fetches from
        Stockbit on a miss. PIT replay mode is cache-only and only reads rows
        fetched on or before as_of_date.
        """
        ticker = ticker.upper()

        if as_of_date is not None:
            return self._cache.read(
                ticker, from_date, to_date, action_type, as_of_date=as_of_date
            )

        if self._api_client is None:
            return self._cache.read(ticker, from_date, to_date, action_type)

        if self._cache.is_fresh(ticker):
            return self._cache.read(ticker, from_date, to_date, action_type)

        transactions = self._fetch(ticker, from_date, to_date, action_type)
        self._cache.write(ticker, transactions)
        return transactions

    def _fetch(
        self, ticker: str, from_date: date, to_date: date, action_type: str
    ) -> list[InsiderTransaction]:
        if self._api_client is None:
            return []
        try:
            action_param = _ACTION_MAP.get(action_type.upper(), "ACTION_TYPE_BUY")
            url = self._stockbit_config.insider_url.format(
                ticker=ticker.upper(),
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
                action_param=action_param,
            )
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty insider response for %s", ticker)
                return []
            txns = _parse_transactions(ticker, body, action_type.upper())
            logger.debug("Insider activity %s → %d transactions", ticker, len(txns))
            return txns
        except Exception as e:
            logger.warning("Insider fetch failed for %s: %s", ticker, e)
            return []
