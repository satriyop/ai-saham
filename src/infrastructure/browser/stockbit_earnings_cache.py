"""
StockbitEarningsCache — SQLite point-in-time cache store for quarterly earnings.

Owns schema creation and legacy primary-key migration, per-row and per-ticker
freshness checks, PIT reads (latest fetched snapshot per year/quarter), single-row
lookups, and record writes for the ``earnings_cache`` table.

Current-quarter fallback walking and API/parser logic stay in
``stockbit_earnings.py`` — this module only exposes read/write/freshness
primitives.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta

from src.domain.value_objects.earnings_record import EarningsRecord
from src.infrastructure.browser.stockbit_pit_cache import (
    safe_cache_write,
    safe_schema_update,
)

logger = logging.getLogger(__name__)

_TTL_DAYS = 7

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS earnings_cache (
    ticker           TEXT NOT NULL,
    year             INTEGER NOT NULL,
    quarter          INTEGER NOT NULL,
    eps_actual       REAL,
    eps_estimate     REAL,
    eps_surprise_pct REAL,
    eps_yoy_change   REAL,
    eps_prev_year    REAL,
    fetched_date     TEXT NOT NULL,
    UNIQUE(ticker, year, quarter, fetched_date)
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_earnings_ticker_period
ON earnings_cache(ticker, year DESC, quarter DESC, fetched_date DESC)
"""


def _rebuild_earnings_cache_if_needed(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(earnings_cache)").fetchall()
    pk_columns = {row["name"] for row in rows if int(row["pk"]) > 0}
    if not pk_columns:
        return
    conn.execute("ALTER TABLE earnings_cache RENAME TO earnings_cache_old")
    conn.execute(_CREATE_TABLE)
    conn.execute(
        """
        INSERT OR IGNORE INTO earnings_cache
            (ticker, year, quarter, eps_actual, eps_estimate, eps_surprise_pct,
             eps_yoy_change, eps_prev_year, fetched_date)
        SELECT ticker, year, quarter, eps_actual, eps_estimate, eps_surprise_pct,
               eps_yoy_change, eps_prev_year, fetched_date
        FROM earnings_cache_old
        """
    )
    conn.execute("DROP TABLE earnings_cache_old")


class StockbitEarningsCache:
    """SQLite-backed PIT cache store for quarterly earnings history."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── Schema ───────────────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        def _update():
            with self._conn as conn:
                conn.execute(_CREATE_TABLE)
                _rebuild_earnings_cache_if_needed(conn)
                conn.execute(_CREATE_TABLE)
                conn.execute(_CREATE_INDEX)

        safe_schema_update(logger=logger, label="earnings_cache", update=_update)

    # ── Freshness ────────────────────────────────────────────────────────────

    def is_row_fresh(self, ticker: str, year: int, quarter: int) -> bool:
        cutoff = (date.today() - timedelta(days=_TTL_DAYS)).isoformat()
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT 1 FROM earnings_cache WHERE ticker=? AND year=? AND quarter=?"
                    " AND fetched_date >= ? LIMIT 1",
                    (ticker.upper(), year, quarter, cutoff),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def is_fresh(self, ticker: str) -> bool:
        """True when any earnings-history snapshot for this ticker is within TTL.

        The current calendar quarter is often not reported yet. Treating that
        missing period as stale causes repeated enrichment fetches that do not
        add usable rows. The refresh gate only needs to know whether the latest
        available earnings history was fetched recently.
        """
        cutoff = (date.today() - timedelta(days=_TTL_DAYS)).isoformat()
        try:
            with self._conn as conn:
                row = conn.execute(
                    "SELECT 1 FROM earnings_cache WHERE ticker=?"
                    " AND date(substr(fetched_date,1,10)) >= date(?) LIMIT 1",
                    (ticker.upper(), cutoff),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    # ── Read ─────────────────────────────────────────────────────────────────

    def read(self, ticker: str, *, as_of_date: date | None = None) -> list[EarningsRecord]:
        """Return every cached quarter for `ticker`, newest first, deduped to
        the latest fetched snapshot per (year, quarter) and eligible as of
        `as_of_date`. Callers apply their own `quarters` limit.
        """
        where = "WHERE e.ticker=?"
        subquery_where = "WHERE ticker=?"
        params: tuple = (ticker.upper(), ticker.upper())
        if as_of_date is not None:
            where += " AND date(substr(fetched_date,1,10)) <= date(?)"
            subquery_where += " AND date(substr(fetched_date,1,10)) <= date(?)"
            params = (
                ticker.upper(),
                as_of_date.isoformat(),
                ticker.upper(),
                as_of_date.isoformat(),
            )
        try:
            with self._conn as conn:
                rows = conn.execute(
                    f"""
                    SELECT e.year, e.quarter, e.eps_actual, e.eps_estimate,
                           e.eps_surprise_pct, e.eps_yoy_change, e.eps_prev_year,
                           e.fetched_date
                    FROM earnings_cache
                    e
                    JOIN (
                        SELECT ticker, year, quarter, MAX(fetched_date) AS max_fetched_date
                        FROM earnings_cache
                        {subquery_where}
                        GROUP BY ticker, year, quarter
                    ) latest
                      ON latest.ticker = e.ticker
                     AND latest.year = e.year
                     AND latest.quarter = e.quarter
                     AND latest.max_fetched_date = e.fetched_date
                    {where}
                    ORDER BY e.year DESC, e.quarter DESC
                    """,
                    params,
                ).fetchall()
        except Exception as e:
            logger.debug("earnings_cache read error for %s: %s", ticker, e)
            return []

        records = []
        for row in rows:
            try:
                raw_fa = row["fetched_date"]
                fetched_at = datetime.fromisoformat(raw_fa) if raw_fa else None
            except ValueError:
                fetched_at = None
            records.append(EarningsRecord(
                ticker=ticker.upper(),
                year=row["year"],
                quarter=row["quarter"],
                eps_actual=row["eps_actual"],
                eps_estimate=row["eps_estimate"],
                eps_surprise_pct=row["eps_surprise_pct"],
                eps_yoy_change=row["eps_yoy_change"],
                eps_prev_year=row["eps_prev_year"],
                fetched_at=fetched_at,
            ))
        return records

    def read_single(self, ticker: str, year: int, quarter: int) -> EarningsRecord | None:
        try:
            with self._conn as conn:
                row = conn.execute(
                    """SELECT year, quarter, eps_actual, eps_estimate,
                              eps_surprise_pct, eps_yoy_change, eps_prev_year, fetched_date
                       FROM earnings_cache
                       WHERE ticker=? AND year=? AND quarter=?
                       ORDER BY fetched_date DESC
                       LIMIT 1""",
                    (ticker.upper(), year, quarter),
                ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        try:
            raw_fa = row["fetched_date"]
            fetched_at = datetime.fromisoformat(raw_fa) if raw_fa else None
        except ValueError:
            fetched_at = None
        return EarningsRecord(
            ticker=ticker.upper(),
            year=row["year"],
            quarter=row["quarter"],
            eps_actual=row["eps_actual"],
            eps_estimate=row["eps_estimate"],
            eps_surprise_pct=row["eps_surprise_pct"],
            eps_yoy_change=row["eps_yoy_change"],
            eps_prev_year=row["eps_prev_year"],
            fetched_at=fetched_at,
        )

    # ── Write ────────────────────────────────────────────────────────────────

    def write_record(self, record: EarningsRecord) -> None:
        now = datetime.now()
        fetched_str = record.fetched_at.isoformat() if record.fetched_at else now.isoformat()

        def _do_write():
            with self._conn as conn:
                conn.execute(
                    """
                    INSERT INTO earnings_cache
                        (ticker, year, quarter, eps_actual, eps_estimate,
                         eps_surprise_pct, eps_yoy_change, eps_prev_year, fetched_date)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ticker, year, quarter, fetched_date) DO UPDATE SET
                        eps_actual=excluded.eps_actual,
                        eps_estimate=excluded.eps_estimate,
                        eps_surprise_pct=excluded.eps_surprise_pct,
                        eps_yoy_change=excluded.eps_yoy_change,
                        eps_prev_year=excluded.eps_prev_year
                    """,
                    (
                        record.ticker,
                        record.year,
                        record.quarter,
                        record.eps_actual,
                        record.eps_estimate,
                        record.eps_surprise_pct,
                        record.eps_yoy_change,
                        record.eps_prev_year,
                        fetched_str,
                    ),
                )

        safe_cache_write(
            logger=logger,
            label="earnings_cache",
            ticker=record.ticker,
            write=_do_write,
        )
