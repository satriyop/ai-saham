"""
StockbitAnalystConsensusProvider — analyst buy/hold/sell ratings from Stockbit.

Calls /analyst-ratings/{ticker} and returns an AnalystConsensus object.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.recommendation             → "Buy" | "Hold" | "Sell"
  data.total_buy                  → int
  data.total_hold                 → int
  data.total_sell                 → int
  data.total_analyst              → int
  data.price_target.best_target    → int (IDR; consensus average)
  data.price_target.best_low_target  → int (IDR; most bearish analyst)
  data.price_target.best_high_target → int (IDR; most bullish analyst)
  data.price_target.current_price  → int (IDR)
  data.last_updated               → "15 Jun 26" (DD Mon YY)

Caching: SQLite daily cache (table: analyst_cache, TTL = 1 calendar day).

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.value_objects.analyst_consensus import AnalystConsensus

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_ANALYST_URL = "https://exodus.stockbit.com/analyst-ratings/{ticker}"


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ("%d %b %y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_consensus(ticker: str, body: dict) -> AnalystConsensus | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    buy = int(data.get("total_buy") or 0)
    hold = int(data.get("total_hold") or 0)
    sell = int(data.get("total_sell") or 0)

    pt = data.get("price_target") or {}
    avg_target = float(pt.get("best_target") or 0) or None
    target_low = float(pt.get("best_low_target") or 0) or None
    target_high = float(pt.get("best_high_target") or 0) or None
    current = float(pt.get("current_price") or 0) or None

    last_updated = _parse_date(str(data.get("last_updated") or ""))

    if buy + hold + sell == 0:
        return None

    return AnalystConsensus(
        ticker=ticker.upper(),
        buy_count=buy,
        hold_count=hold,
        sell_count=sell,
        avg_price_target=avg_target,
        current_price=current,
        last_updated=last_updated,
        price_target_low=target_low,
        price_target_high=target_high,
    )


class StockbitAnalystConsensusProvider(AnalystConsensusProvider):
    """Fetches analyst consensus from Stockbit Exodus API.

    SQLite daily cache (table: analyst_cache, TTL = 1 calendar day).
    Analyst data changes at most daily, so a fresh cache is served directly
    without hitting the API on every swing analyze invocation.

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

    _MIGRATE_COLUMNS = [
        "ALTER TABLE analyst_cache ADD COLUMN price_target_low REAL",
        "ALTER TABLE analyst_cache ADD COLUMN price_target_high REAL",
    ]

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS analyst_cache (
                        ticker             TEXT NOT NULL PRIMARY KEY,
                        buy_count          INTEGER NOT NULL DEFAULT 0,
                        hold_count         INTEGER NOT NULL DEFAULT 0,
                        sell_count         INTEGER NOT NULL DEFAULT 0,
                        avg_price_target   REAL,
                        current_price      REAL,
                        last_updated       TEXT,
                        fetched_date       TEXT NOT NULL,
                        price_target_low   REAL,
                        price_target_high  REAL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_analyst_ticker_fetched
                    ON analyst_cache(ticker, fetched_date)
                """)
                for col_sql in self._MIGRATE_COLUMNS:
                    try:
                        conn.execute(col_sql)
                    except Exception:
                        pass  # column already exists
        except Exception as e:
            logger.warning("analyst_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _is_cache_fresh(self, ticker: str) -> bool:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM analyst_cache WHERE ticker=? AND fetched_date=? LIMIT 1",
                    (ticker.upper(), today_str),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _read_cache(self, ticker: str) -> AnalystConsensus | None:
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT buy_count, hold_count, sell_count,
                           avg_price_target, current_price, last_updated,
                           price_target_low, price_target_high
                    FROM analyst_cache
                    WHERE ticker=?
                    """,
                    (ticker.upper(),),
                ).fetchone()
        except Exception as e:
            logger.debug("analyst_cache read error for %s: %s", ticker, e)
            return None

        if row is None:
            return None
        if row["buy_count"] + row["hold_count"] + row["sell_count"] == 0:
            return None  # sentinel for "fetched but no data"

        return AnalystConsensus(
            ticker=ticker.upper(),
            buy_count=row["buy_count"],
            hold_count=row["hold_count"],
            sell_count=row["sell_count"],
            avg_price_target=row["avg_price_target"],
            current_price=row["current_price"],
            last_updated=_parse_date(row["last_updated"] or ""),
            price_target_low=row["price_target_low"],
            price_target_high=row["price_target_high"],
        )

    def _write_cache(self, ticker: str, consensus: AnalystConsensus | None) -> None:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO analyst_cache
                        (ticker, buy_count, hold_count, sell_count,
                         avg_price_target, current_price, last_updated, fetched_date,
                         price_target_low, price_target_high)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ticker.upper(),
                        consensus.buy_count if consensus else 0,
                        consensus.hold_count if consensus else 0,
                        consensus.sell_count if consensus else 0,
                        consensus.avg_price_target if consensus else None,
                        consensus.current_price if consensus else None,
                        consensus.last_updated.isoformat() if consensus and consensus.last_updated else None,
                        today_str,
                        consensus.price_target_low if consensus else None,
                        consensus.price_target_high if consensus else None,
                    ),
                )
        except Exception as e:
            logger.debug("analyst_cache write error for %s: %s", ticker, e)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_consensus(self, ticker: str) -> AnalystConsensus | None:
        """Return analyst consensus for ticker.

        Checks SQLite cache first (TTL = today). On cache miss, calls the
        Stockbit API and writes results before returning.
        """
        ticker = ticker.upper()

        if self._is_cache_fresh(ticker):
            return self._read_cache(ticker)

        result = self._fetch(ticker)
        self._write_cache(ticker, result)
        return result

    def _fetch(self, ticker: str) -> AnalystConsensus | None:
        if self._provider is None:
            return None
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _ANALYST_URL.format(ticker=ticker.upper())
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty analyst response for %s", ticker)
                return None
            result = _parse_consensus(ticker, body)
            if result:
                logger.debug("Analyst %s → %s (%d analysts)", ticker, result.consensus_label, result.analyst_count)
            return result
        except Exception as e:
            logger.warning("Analyst fetch failed for %s: %s", ticker, e)
            return None
