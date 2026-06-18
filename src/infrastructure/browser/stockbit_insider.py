"""
StockbitInsiderActivityProvider — insider ownership transactions from Stockbit.

Calls /insider/company/majorholder?symbols={ticker}&date_start=...&date_end=...
and returns parsed InsiderTransaction objects (newest first).

Caching: SQLite daily cache (table: insider_cache). TTL = calendar day.
Transactions are stored by (ticker, name, transaction_date, action_type).
On a cache hit for today, query is served from local DB filtered by date range.

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), InsiderActivityProvider port
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
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

    SQLite daily cache (table: insider_cache, TTL = 1 calendar day).
    Transactions are stored per (ticker, name, transaction_date, action_type).
    On a cache hit for today the query is served from DB filtered by date range,
    avoiding a redundant API call on every swing analyze invocation.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
        db_path: Path to the SQLite database (same data.db used by other repos).
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider",
        db_path: str | Path = Path("data.db"),
    ) -> None:
        self._provider = broker_provider
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS insider_cache (
                        ticker                TEXT NOT NULL,
                        name                  TEXT NOT NULL DEFAULT '',
                        role                  TEXT NOT NULL DEFAULT '',
                        action_type           TEXT NOT NULL,
                        shares                INTEGER NOT NULL DEFAULT 0,
                        price                 REAL NOT NULL DEFAULT 0,
                        transaction_date      TEXT NOT NULL,
                        ownership_before_pct  REAL NOT NULL DEFAULT 0,
                        ownership_after_pct   REAL NOT NULL DEFAULT 0,
                        fetched_date          TEXT NOT NULL,
                        PRIMARY KEY (ticker, name, transaction_date, action_type)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_insider_ticker_fetched
                    ON insider_cache(ticker, fetched_date)
                """)
        except Exception as e:
            logger.warning("insider_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _is_cache_fresh(self, ticker: str) -> bool:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM insider_cache WHERE ticker=? AND fetched_date=? LIMIT 1",
                    (ticker.upper(), today_str),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _read_cache(
        self, ticker: str, from_date: date, to_date: date, action_type: str
    ) -> list[InsiderTransaction]:
        try:
            with self._get_conn() as conn:
                if action_type.upper() == "ALL":
                    rows = conn.execute(
                        """
                        SELECT name, role, action_type, shares, price,
                               transaction_date, ownership_before_pct, ownership_after_pct
                        FROM insider_cache
                        WHERE ticker=? AND transaction_date>=? AND transaction_date<=?
                        ORDER BY transaction_date DESC
                        """,
                        (ticker.upper(), from_date.isoformat(), to_date.isoformat()),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT name, role, action_type, shares, price,
                               transaction_date, ownership_before_pct, ownership_after_pct
                        FROM insider_cache
                        WHERE ticker=? AND action_type=? AND transaction_date>=? AND transaction_date<=?
                        ORDER BY transaction_date DESC
                        """,
                        (ticker.upper(), action_type.upper(), from_date.isoformat(), to_date.isoformat()),
                    ).fetchall()
        except Exception as e:
            logger.debug("insider_cache read error for %s: %s", ticker, e)
            return []

        results = []
        for row in rows:
            txn_date = _parse_date(row["transaction_date"])
            if txn_date is None:
                continue
            results.append(InsiderTransaction(
                ticker=ticker.upper(),
                name=row["name"],
                role=row["role"],
                action_type=row["action_type"],
                shares=row["shares"],
                price=row["price"],
                transaction_date=txn_date,
                ownership_before_pct=row["ownership_before_pct"],
                ownership_after_pct=row["ownership_after_pct"],
            ))
        return results

    def _write_cache(self, ticker: str, transactions: list[InsiderTransaction]) -> None:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                # Clear stale entries for this ticker (different day)
                conn.execute(
                    "DELETE FROM insider_cache WHERE ticker=? AND fetched_date!=?",
                    (ticker.upper(), today_str),
                )
                for t in transactions:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO insider_cache
                            (ticker, name, role, action_type, shares, price,
                             transaction_date, ownership_before_pct, ownership_after_pct,
                             fetched_date)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            t.ticker,
                            t.name,
                            t.role,
                            t.action_type,
                            t.shares,
                            t.price,
                            t.transaction_date.isoformat(),
                            t.ownership_before_pct,
                            t.ownership_after_pct,
                            today_str,
                        ),
                    )
                # Sentinel row so _is_cache_fresh() knows we fetched (even if 0 results)
                if not transactions:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO insider_cache
                            (ticker, name, role, action_type, shares, price,
                             transaction_date, ownership_before_pct, ownership_after_pct,
                             fetched_date)
                        VALUES (?, '__NONE__', '', 'NONE', 0, 0, '1970-01-01', 0, 0, ?)
                        """,
                        (ticker.upper(), today_str),
                    )
        except Exception as e:
            logger.debug("insider_cache write error for %s: %s", ticker, e)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
    ) -> list[InsiderTransaction]:
        """Return insider transactions in [from_date, to_date].

        Checks SQLite cache first (TTL = today). On a cache hit, the result is
        filtered by date range and action_type from stored rows. On a cache miss,
        calls the Stockbit API using the requested range and caches all results.
        """
        ticker = ticker.upper()

        if self._is_cache_fresh(ticker):
            return self._read_cache(ticker, from_date, to_date, action_type)

        transactions = self._fetch(ticker, from_date, to_date, action_type)
        self._write_cache(ticker, transactions)
        return transactions

    def _fetch(
        self, ticker: str, from_date: date, to_date: date, action_type: str
    ) -> list[InsiderTransaction]:
        if self._provider is None:
            return []
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
