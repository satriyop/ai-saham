"""
StockbitForwardEstimatesProvider — next-year analyst EPS/Revenue from Stockbit.

Calls /analyst-ratings/{ticker}/consensus and returns a ForwardEstimates object
with forward EPS and Revenue for the next fiscal year.

Actual API shape (confirmed 2026-06-20, BBCA):
  NOTE: data is a LIST, not a dict — different from all other Stockbit endpoints.
  data[].name   → "Revenue" | "Op. Profit" | "Net Income" | "EPS" | ...
  data[].items[].year         → int (fiscal year)
  data[].items[].is_estimate  → bool
  data[].items[].value        → str ("490.46" for EPS, "118,236 B" for Revenue in billions)

  Strategy: for each metric, find the smallest future year where is_estimate=True.
  "B" suffix on Revenue means the raw value is in billions IDR — strip and multiply by 1e9.

Caching: SQLite daily cache (table: forward_estimates_cache, TTL = 1 calendar day).

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )
    from src.infrastructure.config.stockbit_config import StockbitConfig

from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_pit_cache import (
    fetched_at_is_fresh,
    fetched_date_as_of_filter,
    latest_fetched_order,
    safe_cache_read,
    safe_cache_write,
    safe_schema_update,
)
from src.infrastructure.config.stockbit_config import load_stockbit_config

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS forward_estimates_cache (
    ticker              TEXT NOT NULL,
    fetched_date        TEXT NOT NULL,
    forward_eps_1y      REAL,
    revenue_forward_1y  REAL,
    current_price       REAL,
    forward_pe          REAL
)
"""


def _parse_value_str(raw: str | None, is_revenue: bool = False) -> float | None:
    """Parse Stockbit estimate value string to float.

    EPS: "490.46" → 490.46
    Revenue with 'B' suffix: "118,236 B" → 118236000000000 (IDR, multiply by 1e9)
    """
    if not raw:
        return None
    s = str(raw).strip()
    in_billions = s.endswith(" B") or s.endswith("B")
    s = s.rstrip("B").rstrip().replace(",", "")
    try:
        val = float(s)
    except (ValueError, TypeError):
        return None
    if in_billions:
        val = val * 1e9
    return val if val != 0 else None


def _parse_consensus_estimates(ticker: str, body: dict) -> ForwardEstimates | None:
    """Parse /analyst-ratings/{ticker}/consensus response.

    Response: data is a LIST of {name, items[]} objects — not a dict.
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return None

    current_year = date.today().year
    forward_eps: float | None = None
    revenue_fwd: float | None = None

    for section in data:
        if not isinstance(section, dict):
            continue
        name = str(section.get("name") or "").strip()
        items = section.get("items") or []
        if not isinstance(items, list):
            continue

        # Find smallest future year with is_estimate=True
        is_revenue_metric = name == "Revenue"
        is_eps_metric = name == "EPS"
        if not (is_revenue_metric or is_eps_metric):
            continue

        best_year = None
        best_value = None
        for item in items:
            if not isinstance(item, dict):
                continue
            if not item.get("is_estimate"):
                continue
            year = item.get("year")
            try:
                year = int(year)
            except (TypeError, ValueError):
                continue
            if year < current_year:
                continue
            val = _parse_value_str(item.get("value"), is_revenue=is_revenue_metric)
            if val is None:
                continue
            if best_year is None or year < best_year:
                best_year = year
                best_value = val

        if is_eps_metric and best_value is not None:
            forward_eps = best_value
        if is_revenue_metric and best_value is not None:
            revenue_fwd = best_value

    if forward_eps is None and revenue_fwd is None:
        return None

    return ForwardEstimates.compute(
        ticker=ticker.upper(),
        forward_eps_1y=forward_eps,
        revenue_forward_1y=revenue_fwd,
        current_price=None,  # caller may enrich from AnalystConsensus.current_price
        fetched_at=datetime.now(),
    )


def _parse_fetched_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(raw), time.min)
        except (ValueError, TypeError):
            return None


class StockbitForwardEstimatesProvider(ForwardEstimatesProvider, StockbitCachingProvider):
    """Fetches forward EPS/Revenue estimates from Stockbit consensus endpoint.

    SQLite daily cache (table: forward_estimates_cache, TTL = 1 calendar day).
    Analyst estimates change at most daily.
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
        super().__init__(
            api_client,
            db_path,
            connection_provider=connection_provider,
        )

    def _ensure_schema(self) -> None:
        def _update():
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(_CREATE_TABLE)
                _rebuild_forward_estimates_cache_if_needed(conn)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_forward_estimates_ticker_fetched "
                    "ON forward_estimates_cache(ticker, fetched_date)"
                )

        safe_schema_update(logger=logger, label="forward_estimates_cache", update=_update)

    def get_forward_estimates(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> ForwardEstimates | None:
        ticker = ticker.upper()
        if as_of_date is not None:
            return self._read_cache(
                ticker,
                require_fresh=False,
                as_of_date=as_of_date,
            )
        cached = self._read_cache(ticker, require_fresh=self._api_client is not None)
        if cached is not None:
            return cached
        result = self._fetch(ticker)
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(
        self,
        ticker: str,
        require_fresh: bool = True,
        as_of_date: date | None = None,
    ) -> ForwardEstimates | None:
        where = "WHERE ticker=?"
        params: tuple[str, ...] = (ticker,)
        frag, extra_params = fetched_date_as_of_filter(as_of_date)
        where += frag
        params += extra_params

        def _do_read():
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT fetched_date, forward_eps_1y, revenue_forward_1y, "
                    "current_price, forward_pe "
                    f"FROM forward_estimates_cache {where} "
                    f"{latest_fetched_order()} LIMIT 1",
                    params,
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if require_fresh and not fetched_at_is_fresh(fetched_at, ttl_days=0):
                return None
            return ForwardEstimates(
                ticker=ticker,
                forward_eps_1y=row[1],
                revenue_forward_1y=row[2],
                current_price=row[3],
                forward_pe=row[4],
                fetched_at=fetched_at,
            )

        return safe_cache_read(
            logger=logger,
            label="forward_estimates_cache",
            ticker=ticker,
            default=None,
            read=_do_read,
        )

    def _write_cache(self, est: ForwardEstimates) -> None:
        fetched_str = est.fetched_at.isoformat() if est.fetched_at else datetime.now().isoformat()

        def _do_write():
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO forward_estimates_cache "
                    "(ticker, fetched_date, forward_eps_1y, revenue_forward_1y, "
                    "current_price, forward_pe) VALUES (?,?,?,?,?,?)",
                    (
                        est.ticker,
                        fetched_str,
                        est.forward_eps_1y,
                        est.revenue_forward_1y,
                        est.current_price,
                        est.forward_pe,
                    ),
                )

        safe_cache_write(
            logger=logger,
            label="forward_estimates_cache",
            ticker=est.ticker,
            write=_do_write,
        )

    def _fetch(self, ticker: str) -> ForwardEstimates | None:
        if self._api_client is None:
            return None
        try:
            url = self._stockbit_config.analyst_consensus_url.format(ticker=ticker)
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty forward estimates response for %s", ticker)
                return None
            result = _parse_consensus_estimates(ticker, body)
            if result:
                logger.debug(
                    "ForwardEstimates %s → EPS=%.2f forward_PE=%.1f",
                    ticker,
                    result.forward_eps_1y or 0,
                    result.forward_pe or 0,
                )
            return result
        except Exception as e:
            logger.warning("Forward estimates fetch failed for %s: %s", ticker, e)
            return None


def _rebuild_forward_estimates_cache_if_needed(sqlite_conn: sqlite3.Connection) -> None:
    rows = sqlite_conn.execute("PRAGMA table_info(forward_estimates_cache)").fetchall()
    ticker_pk = any(row[1] == "ticker" and int(row[5]) > 0 for row in rows)
    if not ticker_pk:
        return
    sqlite_conn.execute("ALTER TABLE forward_estimates_cache RENAME TO forward_estimates_cache_old")
    sqlite_conn.execute(_CREATE_TABLE)
    sqlite_conn.execute(
        """
        INSERT INTO forward_estimates_cache
            (ticker, fetched_date, forward_eps_1y, revenue_forward_1y,
             current_price, forward_pe)
        SELECT ticker, fetched_date, forward_eps_1y, revenue_forward_1y,
               current_price, forward_pe
        FROM forward_estimates_cache_old
        """
    )
    sqlite_conn.execute("DROP TABLE forward_estimates_cache_old")
