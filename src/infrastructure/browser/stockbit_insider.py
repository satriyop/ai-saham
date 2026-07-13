"""
StockbitInsiderActivityProvider — insider ownership transactions from Stockbit.

Calls /insider/company/majorholder?symbols={ticker}&date_start=...&date_end=...
and returns parsed InsiderTransaction objects (newest first).

Caching: SQLite daily cache (table: insider_cache). TTL = calendar day for live
mode. Historical replay is point-in-time: cache-only, limited to rows fetched on
or before the requested as-of date.

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), InsiderActivityProvider port
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime

from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_pit_cache import (
    safe_cache_write,
    safe_schema_update,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

_INSIDER_URL = STOCKBIT_CFG.insider_url

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

    SQLite daily cache (table: insider_cache, TTL = 1 calendar day for live mode).
    Transactions are stored per
    (ticker, name, transaction_date, action_type, fetched_date) so historical
    snapshots remain available for point-in-time replay.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
        db_path: Path to the SQLite database (same data.db used by other repos).
    """

    # ── Schema ───────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        def _update():
            with self._get_conn() as conn:
                self._ensure_pit_schema(conn)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_insider_ticker_fetched
                    ON insider_cache(ticker, fetched_date)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_insider_ticker_txn_fetched
                    ON insider_cache(ticker, transaction_date, action_type, fetched_date)
                """)

        safe_schema_update(logger=logger, label="insider_cache", update=_update)

    def _ensure_pit_schema(self, conn: sqlite3.Connection) -> None:
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
                PRIMARY KEY (ticker, name, transaction_date, action_type, fetched_date)
            )
        """)
        pk_cols = [
            row["name"]
            for row in sorted(
                conn.execute("PRAGMA table_info(insider_cache)").fetchall(),
                key=lambda r: r["pk"],
            )
            if row["pk"] > 0
        ]
        if pk_cols == [
            "ticker",
            "name",
            "transaction_date",
            "action_type",
            "fetched_date",
        ]:
            return

        conn.execute("ALTER TABLE insider_cache RENAME TO insider_cache_old")
        conn.execute("""
            CREATE TABLE insider_cache (
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
                PRIMARY KEY (ticker, name, transaction_date, action_type, fetched_date)
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO insider_cache
                (ticker, name, role, action_type, shares, price, transaction_date,
                 ownership_before_pct, ownership_after_pct, fetched_date)
            SELECT ticker, name, role, action_type, shares, price, transaction_date,
                   ownership_before_pct, ownership_after_pct, fetched_date
            FROM insider_cache_old
        """)
        conn.execute("DROP TABLE insider_cache_old")

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
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str,
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]:
        try:
            with self._get_conn() as conn:
                if self._latest_eligible_snapshot_is_empty(
                    conn,
                    ticker=ticker,
                    from_date=from_date,
                    to_date=to_date,
                    action_type=action_type,
                    as_of_date=as_of_date,
                ):
                    return []
                params: list[str] = [
                    ticker.upper(),
                    from_date.isoformat(),
                    to_date.isoformat(),
                ]
                as_of_filter = ""
                if as_of_date is not None:
                    as_of_filter = "AND fetched_date<=?"
                    params.append(as_of_date.isoformat())
                action_filter = ""
                if action_type.upper() != "ALL":
                    action_filter = "AND action_type=?"
                    params.append(action_type.upper())

                query = f"""
                    SELECT c.name, c.role, c.action_type, c.shares, c.price,
                           c.transaction_date, c.ownership_before_pct,
                           c.ownership_after_pct
                    FROM insider_cache c
                    JOIN (
                        SELECT ticker, name, transaction_date, action_type,
                               MAX(fetched_date) AS fetched_date
                        FROM insider_cache
                        WHERE ticker=?
                          AND transaction_date>=?
                          AND transaction_date<=?
                          AND name!='__NONE__'
                          {as_of_filter}
                          {action_filter}
                        GROUP BY ticker, name, transaction_date, action_type
                    ) latest
                      ON latest.ticker=c.ticker
                     AND latest.name=c.name
                     AND latest.transaction_date=c.transaction_date
                     AND latest.action_type=c.action_type
                     AND latest.fetched_date=c.fetched_date
                    ORDER BY c.transaction_date DESC, c.fetched_date DESC
                """
                rows = conn.execute(query, tuple(params)).fetchall()
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

    def _latest_eligible_snapshot_is_empty(
        self,
        conn: sqlite3.Connection,
        *,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str,
        as_of_date: date | None,
    ) -> bool:
        params: list[str] = [ticker.upper()]
        as_of_filter = ""
        if as_of_date is not None:
            as_of_filter = "AND fetched_date<=?"
            params.append(as_of_date.isoformat())
        row = conn.execute(
            f"""
            SELECT fetched_date
            FROM insider_cache
            WHERE ticker=?
              {as_of_filter}
            ORDER BY fetched_date DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        if row is None:
            return False

        latest_fetched_date = row["fetched_date"]
        sentinel = conn.execute(
            """
            SELECT 1
            FROM insider_cache
            WHERE ticker=? AND fetched_date=? AND name='__NONE__'
            LIMIT 1
            """,
            (ticker.upper(), latest_fetched_date),
        ).fetchone()
        if sentinel is None:
            return False

        real_params: list[str] = [
            ticker.upper(),
            latest_fetched_date,
            from_date.isoformat(),
            to_date.isoformat(),
        ]
        action_filter = ""
        if action_type.upper() != "ALL":
            action_filter = "AND action_type=?"
            real_params.append(action_type.upper())
        real_row = conn.execute(
            f"""
            SELECT 1
            FROM insider_cache
            WHERE ticker=?
              AND fetched_date=?
              AND name!='__NONE__'
              AND transaction_date>=?
              AND transaction_date<=?
              {action_filter}
            LIMIT 1
            """,
            tuple(real_params),
        ).fetchone()
        return real_row is None

    def _write_cache(self, ticker: str, transactions: list[InsiderTransaction]) -> None:
        _ticker = ticker.upper()
        today_str = date.today().isoformat()

        def _do_write():
            with self._get_conn() as conn:
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
                        (_ticker, today_str),
                    )

        safe_cache_write(
            logger=logger,
            label="insider_cache",
            ticker=ticker,
            write=_do_write,
        )

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
            return self._read_cache(
                ticker,
                from_date,
                to_date,
                action_type,
                as_of_date=as_of_date,
            )

        if self._api_client is None:
            return self._read_cache(ticker, from_date, to_date, action_type)

        if self._is_cache_fresh(ticker):
            return self._read_cache(ticker, from_date, to_date, action_type)

        transactions = self._fetch(ticker, from_date, to_date, action_type)
        self._write_cache(ticker, transactions)
        return transactions

    def _fetch(
        self, ticker: str, from_date: date, to_date: date, action_type: str
    ) -> list[InsiderTransaction]:
        if self._api_client is None:
            return []
        try:
            action_param = _ACTION_MAP.get(action_type.upper(), "ACTION_TYPE_BUY")
            url = _INSIDER_URL.format(
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
