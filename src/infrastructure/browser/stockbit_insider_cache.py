"""
StockbitInsiderCache — SQLite point-in-time cache store for insider transactions.

Owns schema creation and legacy primary-key migration, daily freshness checks,
PIT reads (deduped to the latest fetched snapshot per logical transaction),
and writes (including the ``__NONE__`` sentinel row used to remember that a
fetch legitimately returned no transactions) for the ``insider_cache`` table.

No API/client/parser logic lives here — that stays in
``stockbit_insider.py``.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime

from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_pit_cache import (
    safe_cache_write,
    safe_schema_update,
)

logger = logging.getLogger(__name__)


def _parse_cached_date(raw: str) -> date | None:
    """Parse a transaction_date value stored in insider_cache (ISO format)."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


class StockbitInsiderCache:
    """SQLite-backed PIT cache store for insider transactions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Schema ───────────────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        def _update():
            with self._conn as conn:
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

    # ── Freshness ────────────────────────────────────────────────────────────

    def is_fresh(self, ticker: str) -> bool:
        today_str = date.today().isoformat()
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT 1 FROM insider_cache WHERE ticker=? AND fetched_date=? LIMIT 1",
                    (ticker.upper(), today_str),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    # ── Read ─────────────────────────────────────────────────────────────────

    def read(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str,
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]:
        """Return cached transactions for `ticker` in [from_date, to_date],
        deduped to the latest fetched snapshot per logical transaction,
        eligible as of `as_of_date`.
        """
        try:
            with self._conn as conn:
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
            txn_date = _parse_cached_date(row["transaction_date"])
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

    # ── Write ────────────────────────────────────────────────────────────────

    def write(self, ticker: str, transactions: list[InsiderTransaction]) -> None:
        _ticker = ticker.upper()
        today_str = date.today().isoformat()

        def _do_write():
            with self._conn as conn:
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
                # Sentinel row so is_fresh() knows we fetched (even if 0 results)
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
