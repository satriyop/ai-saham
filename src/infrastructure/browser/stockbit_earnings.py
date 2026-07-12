"""
StockbitEarningsProvider — quarterly EPS history from Stockbit /earnings endpoint.

Fetches up to N quarters by walking the prev_earnings_period chain in the API response.
Each quarter is cached independently so subsequent calls only re-fetch stale rows.

Actual API shape (confirmed 2026-06-20, BBCA Q1 2026):
  URL: /earnings?keyword={ticker}&quarter={q}&year={y}
  data.quarter                         → current period quarter (int)
  data.year                            → current period year (str)
  data.prev_earnings_period.quarter    → prior period quarter (str, "" = none)
  data.prev_earnings_period.year       → prior period year (str, "" = none)
  data.company[0].analyst.consensus.actual    → EPS actual (str, e.g. "119.12")
  data.company[0].analyst.consensus.estimate  → EPS estimate (str, "-" if none)
  data.company[0].analyst.consensus.surprise  → surprise (str, "-" if none)
  data.company[0].analyst.prevyear.change     → YoY change in EPS (str)
  data.company[0].analyst.prevyear.previous   → prior year EPS (str)

Caching: SQLite table `earnings_cache`, TTL = 7 days.
  PIT key: unique (ticker, year, quarter, fetched_date)

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.earnings_provider import EarningsProvider
from src.domain.value_objects.earnings_record import EarningsRecord

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_EARNINGS_URL = STOCKBIT_CFG.earnings_url

_TTL_DAYS = 7
_DEFAULT_QUARTERS = 4


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


def _parse_float(raw: str | None) -> float | None:
    if not raw or str(raw).strip() in ("-", "", "null", "None"):
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_period_record(ticker: str, quarter: int, year: int, body: dict) -> EarningsRecord | None:
    """Parse one /earnings response into an EarningsRecord."""
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    companies = data.get("company") or []
    if not companies:
        return None

    company = companies[0]
    analyst = company.get("analyst") or {}
    consensus = analyst.get("consensus") or {}
    prevyear = analyst.get("prevyear") or {}

    eps_actual = _parse_float(consensus.get("actual"))
    eps_estimate = _parse_float(consensus.get("estimate"))
    surprise_raw = _parse_float(consensus.get("surprise"))

    # Compute surprise % if not directly provided
    eps_surprise_pct: float | None = None
    if surprise_raw is not None:
        eps_surprise_pct = surprise_raw
    elif eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
        eps_surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate) * 100

    eps_yoy_change = _parse_float(prevyear.get("change"))
    eps_prev_year = _parse_float(prevyear.get("previous"))

    if eps_actual is None:
        return None  # no meaningful data

    return EarningsRecord(
        ticker=ticker.upper(),
        year=year,
        quarter=quarter,
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        eps_surprise_pct=eps_surprise_pct,
        eps_yoy_change=eps_yoy_change,
        eps_prev_year=eps_prev_year,
        fetched_at=datetime.now(),
    )


def _next_prev_period(body: dict) -> tuple[int, int] | None:
    """Return (quarter, year) of the previous earnings period, or None if end of history."""
    data = body.get("data") if isinstance(body, dict) else {}
    prev = (data or {}).get("prev_earnings_period") or {}
    q_str = str(prev.get("quarter") or "").strip()
    y_str = str(prev.get("year") or "").strip()
    if not q_str or not y_str:
        return None
    try:
        return int(q_str), int(y_str)
    except ValueError:
        return None


def _current_quarter_year() -> tuple[int, int]:
    today = date.today()
    return (today.month - 1) // 3 + 1, today.year


class StockbitEarningsProvider(EarningsProvider, StockbitCachingProvider):
    """Fetches quarterly EPS history from Stockbit /earnings endpoint.

    Walks the prev_earnings_period chain to collect up to `quarters` records.
    Each record is stored independently; stale records are re-fetched individually.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
        db_path: Path to the SQLite database.
    """

    # ── Schema ───────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute(_CREATE_TABLE)
                _rebuild_earnings_cache_if_needed(conn)
                conn.execute(_CREATE_TABLE)
                conn.execute(_CREATE_INDEX)
        except Exception as e:
            logger.warning("earnings_cache schema error: %s", e)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _is_row_fresh(self, ticker: str, year: int, quarter: int) -> bool:
        cutoff = (date.today() - timedelta(days=_TTL_DAYS)).isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM earnings_cache WHERE ticker=? AND year=? AND quarter=?"
                    " AND fetched_date >= ? LIMIT 1",
                    (ticker.upper(), year, quarter, cutoff),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def is_cache_fresh(self, ticker: str) -> bool:
        """True when any earnings-history snapshot for this ticker is within TTL.

        The current calendar quarter is often not reported yet. Treating that
        missing period as stale causes repeated enrichment fetches that do not
        add usable rows. The refresh gate only needs to know whether the latest
        available earnings history was fetched recently.
        """
        cutoff = (date.today() - timedelta(days=_TTL_DAYS)).isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM earnings_cache WHERE ticker=?"
                    " AND date(substr(fetched_date,1,10)) >= date(?) LIMIT 1",
                    (ticker.upper(), cutoff),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _read_cache(
        self,
        ticker: str,
        quarters: int,
        as_of_date: date | None = None,
    ) -> list[EarningsRecord]:
        where = "WHERE e.ticker=?"
        subquery_where = "WHERE ticker=?"
        params: tuple = (ticker.upper(), ticker.upper(), quarters)
        if as_of_date is not None:
            where += " AND date(substr(fetched_date,1,10)) <= date(?)"
            subquery_where += " AND date(substr(fetched_date,1,10)) <= date(?)"
            params = (
                ticker.upper(),
                as_of_date.isoformat(),
                ticker.upper(),
                as_of_date.isoformat(),
                quarters,
            )
        try:
            with self._get_conn() as conn:
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
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        except Exception as e:
            logger.debug("earnings_cache read error for %s: %s", ticker, e)
            return []

        records = []
        for row in rows:
            try:
                fetched_at = datetime.fromisoformat(row["fetched_date"]) if row["fetched_date"] else None
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

    def _write_record(self, record: EarningsRecord) -> None:
        fetched_str = record.fetched_at.isoformat() if record.fetched_at else datetime.now().isoformat()
        try:
            with self._get_conn() as conn:
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
        except Exception as e:
            logger.debug("earnings_cache write error for %s Q%s %s: %s",
                         record.ticker, record.quarter, record.year, e)

    # ── Port implementation ───────────────────────────────────────────────────

    def get_earnings_history(
        self,
        ticker: str,
        quarters: int = _DEFAULT_QUARTERS,
        as_of_date: date | None = None,
    ) -> list[EarningsRecord]:
        """Return up to `quarters` most recent earnings records, newest first.

        Fetches fresh data from API for any quarter outside the 7-day TTL.
        Falls back to cached data when API is unavailable.
        """
        ticker = ticker.upper()

        if as_of_date is not None:
            return self._read_cache(ticker, quarters, as_of_date=as_of_date)

        # Check if current quarter is fresh — if so, serve fully from cache
        if self.is_cache_fresh(ticker):
            cached = self._read_cache(ticker, quarters)
            if cached:
                return cached

        # Fetch from API, walking backwards through prev_earnings_period
        fetched = self._fetch_quarters(ticker, quarters)
        if fetched:
            for record in fetched:
                self._write_record(record)
            return fetched

        # API unavailable — fall back to whatever is cached
        return self._read_cache(ticker, quarters)

    def _fetch_quarters(self, ticker: str, quarters: int) -> list[EarningsRecord]:
        if self._api_client is None:
            return []

        records: list[EarningsRecord] = []
        current_q, current_y = _current_quarter_year()

        consecutive_failures = 0
        max_failures = 4  # Try up to 1 year back to find the first reported quarter

        while len(records) < quarters and consecutive_failures < max_failures:
            if self._is_row_fresh(ticker, current_y, current_q):
                # Row already cached and fresh — load from cache and still get prev period pointer
                cached_rows = self._read_cache_single(ticker, current_y, current_q)
                if cached_rows:
                    records.append(cached_rows)
                    consecutive_failures = 0
                # We still need to know the prev_period to continue the walk.
                # Try fetching just to get the pointer without writing.
                body = self._do_get(ticker, current_q, current_y)
                prev = _next_prev_period(body) if body else None
            else:
                body = self._do_get(ticker, current_q, current_y)
                if body:
                    record = _parse_period_record(ticker, current_q, current_y, body)
                    if record:
                        records.append(record)
                        consecutive_failures = 0
                    prev = _next_prev_period(body)
                else:
                    prev = None

            if prev is not None:
                current_q, current_y = prev
            else:
                # If we haven't found any records yet, walk backward to search for the latest reported quarter
                if not records:
                    consecutive_failures += 1
                    current_q -= 1
                    if current_q == 0:
                        current_q = 4
                        current_y -= 1
                else:
                    break

        return records

    def _do_get(self, ticker: str, quarter: int, year: int) -> dict | None:
        try:
            url = _EARNINGS_URL.format(ticker=ticker, quarter=quarter, year=year)
            return self._api_client.get(url)
        except Exception as e:
            logger.debug("Earnings GET failed for %s Q%s %s: %s", ticker, quarter, year, e)
            return None

    def _read_cache_single(self, ticker: str, year: int, quarter: int) -> EarningsRecord | None:
        try:
            with self._get_conn() as conn:
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
            fetched_at = datetime.fromisoformat(row["fetched_date"]) if row["fetched_date"] else None
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
