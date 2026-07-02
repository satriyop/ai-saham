"""
StockbitSeasonalityProvider — monthly seasonality data from Stockbit Exodus API.

Calls /company-price-feed/seasonality/{ticker}?year={year}&back_year={back_years}
and extracts the avg monthly return and win-rate for the requested month.

Caching: SQLite monthly cache (table: seasonality_cache). TTL = current calendar
month, since seasonality data only changes when the month rolls over.

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), SeasonalityProvider port
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.seasonality_provider import SeasonalityProvider
from src.domain.value_objects.seasonal_edge import SeasonalEdge

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_SEASONALITY_URL = STOCKBIT_CFG.seasonality_url

# Stockbit uses abbreviated English month names as column keys
_MONTH_TO_NAME = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _col_value(section: dict, month_name: str) -> str | None:
    """Extract the value for a named column from a {columns: [{name, value}]} section."""
    for col in section.get("columns", []):
        if col.get("name") == month_name:
            return col.get("value")
    return None


def _parse_seasonality(ticker: str, month: int, back_years: int, body: dict) -> SeasonalEdge | None:
    """Parse /seasonality/{ticker} response for one target month.

    Actual Stockbit Exodus response shape (confirmed 2026-06):
      data.avg.columns[]         — [{name: "Jun", value: "0.87"}]  avg return %
      data.prob.columns[]        — [{name: "Jun", value: "60"}]    win rate %
      data.up.columns[]          — [{name: "Jun", value: "3"}]     positive years
      data.total_months.columns[]— [{name: "Jun", value: "5"}]     total years
      data.default_last_year     — int, number of back years used
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        logger.debug("Unexpected seasonality response shape for %s", ticker)
        return None

    month_name = _MONTH_TO_NAME.get(month)
    if not month_name:
        return None

    avg_section = data.get("avg", {})
    prob_section = data.get("prob", {})
    up_section = data.get("up", {})
    total_section = data.get("total_months", {})

    raw_avg = _col_value(avg_section, month_name)
    raw_prob = _col_value(prob_section, month_name)
    raw_up = _col_value(up_section, month_name)
    raw_total = _col_value(total_section, month_name)

    try:
        avg_return = float(raw_avg)
    except (TypeError, ValueError):
        logger.debug("No avg return for %s month=%d", ticker, month)
        return None

    try:
        win_rate = float(raw_prob)
    except (TypeError, ValueError):
        logger.debug("No win rate for %s month=%d", ticker, month)
        return None

    try:
        positive_years = int(raw_up)
    except (TypeError, ValueError):
        positive_years = round(win_rate / 100.0 * back_years)

    try:
        total_years = int(raw_total)
    except (TypeError, ValueError):
        total_years = data.get("default_last_year", back_years)

    return SeasonalEdge(
        ticker=ticker.upper(),
        month=month,
        avg_monthly_return_pct=round(avg_return, 2),
        win_rate_pct=round(win_rate, 1),
        positive_years=positive_years,
        total_years=total_years,
        back_years=back_years,
        source="stockbit",
        fetched_at=datetime.now(),
    )


class StockbitSeasonalityProvider(SeasonalityProvider, StockbitCachingProvider):
    """
    Fetches monthly seasonality from Stockbit.

    SQLite daily cache (table: seasonality_cache). TTL = current calendar month,
    since Stockbit aggregates across historical years and the result only changes
    when a new month completes.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
        db_path: Path to the SQLite database (same data.db used by other repos).
    """

    # ── Schema ───────────────────────────────────────────────────────────────

    _MIGRATIONS: list[tuple[int, str]] = [
        (0, """CREATE TABLE IF NOT EXISTS seasonality_cache (
                        ticker           TEXT NOT NULL,
                        year             INTEGER NOT NULL,
                        month            INTEGER NOT NULL,
                        avg_return_pct   REAL,
                        win_rate_pct     REAL,
                        positive_years   INTEGER,
                        total_years      INTEGER,
                        back_years       INTEGER,
                        source           TEXT,
                        fetched_month    TEXT NOT NULL,
                        fetched_at       TEXT,
                        PRIMARY KEY (ticker, year, month)
                    )"""),
        (1, "CREATE INDEX IF NOT EXISTS idx_seasonality_ticker_month ON seasonality_cache(ticker, fetched_month)"),
        (2, "ALTER TABLE seasonality_cache ADD COLUMN fetched_at TEXT"),
    ]

    def _ensure_schema(self) -> None:
        try:
            SqliteMigrationRunner(self._db_path).run("seasonality_cache", self._MIGRATIONS)
        except Exception as e:
            logger.warning("seasonality_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _current_month_key(self) -> str:
        """Return YYYY-MM string for the current calendar month."""
        today = date.today()
        return f"{today.year:04d}-{today.month:02d}"

    def _is_cache_fresh(self, ticker: str, year: int, month: int) -> bool:
        month_key = self._current_month_key()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM seasonality_cache WHERE ticker=? AND year=? AND month=? AND fetched_month=? LIMIT 1",
                    (ticker.upper(), year, month, month_key),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _read_cache(self, ticker: str, year: int, month: int) -> SeasonalEdge | None:
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT avg_return_pct, win_rate_pct, positive_years,
                           total_years, back_years, source, fetched_at
                    FROM seasonality_cache
                    WHERE ticker=? AND year=? AND month=?
                    """,
                    (ticker.upper(), year, month),
                ).fetchone()
        except Exception as e:
            logger.debug("seasonality_cache read error for %s: %s", ticker, e)
            return None

        if row is None:
            return None
        if row["avg_return_pct"] is None or row["win_rate_pct"] is None:
            return None  # sentinel for "fetched but no data"
        if row["positive_years"] is None or row["total_years"] is None or row["back_years"] is None:
            return None

        fetched_at: datetime | None = None
        raw_fa = row["fetched_at"]
        if raw_fa:
            try:
                fetched_at = datetime.fromisoformat(raw_fa)
            except (ValueError, TypeError):
                pass

        return SeasonalEdge(
            ticker=ticker.upper(),
            month=month,
            avg_monthly_return_pct=row["avg_return_pct"],
            win_rate_pct=row["win_rate_pct"],
            positive_years=row["positive_years"],
            total_years=row["total_years"],
            back_years=row["back_years"],
            source=row["source"] or "stockbit",
            fetched_at=fetched_at,
        )

    def _write_cache(self, ticker: str, year: int, month: int, edge: SeasonalEdge | None) -> None:
        month_key = self._current_month_key()
        fetched_str = (
            edge.fetched_at.isoformat() if edge and edge.fetched_at else datetime.now().isoformat()
        )
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO seasonality_cache
                        (ticker, year, month, avg_return_pct, win_rate_pct,
                         positive_years, total_years, back_years, source, fetched_month, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ticker.upper(),
                        year,
                        month,
                        edge.avg_monthly_return_pct if edge else None,
                        edge.win_rate_pct if edge else None,
                        edge.positive_years if edge else None,
                        edge.total_years if edge else None,
                        edge.back_years if edge else None,
                        edge.source if edge else None,
                        month_key,
                        fetched_str,
                    ),
                )
        except Exception as e:
            logger.debug("seasonality_cache write error for %s: %s", ticker, e)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_seasonal_edge(
        self,
        ticker: str,
        year: int,
        month: int,
        back_years: int = 5,
    ) -> SeasonalEdge | None:
        """Return SeasonalEdge for ticker in given year/month.

        Checks SQLite cache first (TTL = current calendar month). On cache miss,
        calls the Stockbit API and writes results before returning.
        """
        ticker = ticker.upper()

        if self._is_cache_fresh(ticker, year, month):
            return self._read_cache(ticker, year, month)

        result = self._fetch(ticker, year, month, back_years)
        self._write_cache(ticker, year, month, result)
        return result

    def _fetch(self, ticker: str, year: int, month: int, back_years: int) -> SeasonalEdge | None:
        if self._api_client is None:
            return None
        try:
            url = _SEASONALITY_URL.format(
                ticker=ticker.upper(),
                year=year,
                back_years=back_years,
            )
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty seasonality response for %s", ticker)
                return None
            edge = _parse_seasonality(ticker, month, back_years, body)
            if edge:
                logger.debug("Seasonality %s month=%d → %s", ticker, month, edge.label)
            return edge
        except Exception as e:
            logger.warning("Seasonality fetch failed for %s: %s", ticker, e)
            return None
