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
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.value_objects.analyst_consensus import AnalystConsensus

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )
    from src.infrastructure.config.stockbit_config import StockbitConfig

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import load_stockbit_config
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

logger = logging.getLogger(__name__)


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ("%d %b %y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_fetched_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            from datetime import date as _date

            return datetime.combine(_date.fromisoformat(raw), datetime.min.time())
        except (ValueError, TypeError):
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
        fetched_at=datetime.now(),
    )


class StockbitAnalystConsensusProvider(AnalystConsensusProvider, StockbitCachingProvider):
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
        api_client: "StockbitApiClient | None",
        db_path: Path | str = Path("data.db"),
        *,
        connection_provider: "StockbitSQLiteConnectionProvider | None" = None,
        stockbit_config: StockbitConfig | None = None,
    ) -> None:
        self._stockbit_config = stockbit_config or load_stockbit_config()
        super().__init__(api_client, db_path, connection_provider=connection_provider)

    # ── Schema ───────────────────────────────────────────────────────────────

    _MIGRATIONS: list[tuple[int, str]] = [
        (
            0,
            """CREATE TABLE IF NOT EXISTS analyst_cache (
                        ticker             TEXT NOT NULL,
                        buy_count          INTEGER NOT NULL DEFAULT 0,
                        hold_count         INTEGER NOT NULL DEFAULT 0,
                        sell_count         INTEGER NOT NULL DEFAULT 0,
                        avg_price_target   REAL,
                        current_price      REAL,
                        last_updated       TEXT,
                        fetched_date       TEXT NOT NULL,
                        price_target_low   REAL,
                        price_target_high  REAL,
                        UNIQUE(ticker, fetched_date)
                    )""",
        ),
    ]

    def _ensure_schema(self) -> None:
        try:
            SqliteMigrationRunner(self._db_path).run("analyst_cache", self._MIGRATIONS)
        except Exception as e:
            logger.warning("analyst_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _is_cache_fresh(self, ticker: str) -> bool:
        today_str = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM analyst_cache WHERE ticker=?"
                    " AND substr(fetched_date,1,10)=? LIMIT 1",
                    (ticker.upper(), today_str),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def read_cached(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> AnalystConsensus | None:
        """Public cache-only read. Never fetches from network."""
        return self._read_cache(ticker, as_of_date=as_of_date)

    def _read_cache(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> AnalystConsensus | None:
        where = "WHERE ticker=?"
        params: tuple[str, ...] = (ticker.upper(),)
        if as_of_date is not None:
            where += " AND date(substr(fetched_date,1,10)) <= date(?)"
            params = (ticker.upper(), as_of_date.isoformat())
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    f"""
                    SELECT buy_count, hold_count, sell_count,
                           avg_price_target, current_price, last_updated,
                           price_target_low, price_target_high, fetched_date
                    FROM analyst_cache
                    {where}
                    ORDER BY date(substr(fetched_date,1,10)) DESC, fetched_date DESC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()
        except Exception as e:
            logger.debug("analyst_cache read error for %s: %s", ticker, e)
            return None

        if row is None:
            return None
        if row["buy_count"] + row["hold_count"] + row["sell_count"] == 0:
            return None  # sentinel for "fetched but no data"

        fetched_at = _parse_fetched_at(row["fetched_date"])
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
            fetched_at=fetched_at,
        )

    def _write_cache(self, ticker: str, consensus: AnalystConsensus | None) -> None:
        fetched_str = (
            consensus.fetched_at.isoformat()
            if consensus and consensus.fetched_at
            else datetime.now().isoformat()
        )
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO analyst_cache
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
                        (
                            consensus.last_updated.isoformat()
                            if consensus and consensus.last_updated
                            else None
                        ),
                        fetched_str,
                        consensus.price_target_low if consensus else None,
                        consensus.price_target_high if consensus else None,
                    ),
                )
        except Exception as e:
            logger.debug("analyst_cache write error for %s: %s", ticker, e)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_consensus(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> AnalystConsensus | None:
        """Return analyst consensus for ticker.

        Checks SQLite cache first (TTL = today). On cache miss, calls the
        Stockbit API and writes results before returning.
        """
        ticker = ticker.upper()

        if as_of_date is not None:
            return self._read_cache(ticker, as_of_date=as_of_date)

        if self._api_client is None:
            return self._read_cache(ticker)

        if self._is_cache_fresh(ticker):
            return self._read_cache(ticker)

        result = self._fetch(ticker)
        self._write_cache(ticker, result)
        return result

    def _fetch(self, ticker: str) -> AnalystConsensus | None:
        if self._api_client is None:
            return None
        try:
            url = self._stockbit_config.analyst_url.format(ticker=ticker.upper())
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty analyst response for %s", ticker)
                return None
            result = _parse_consensus(ticker, body)
            if result:
                logger.debug(
                    "Analyst %s → %s (%d analysts)",
                    ticker,
                    result.consensus_label,
                    result.analyst_count,
                )
            return result
        except Exception as e:
            logger.warning("Analyst fetch failed for %s: %s", ticker, e)
            return None
