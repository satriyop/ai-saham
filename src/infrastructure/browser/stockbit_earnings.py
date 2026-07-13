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

Caching: delegated to StockbitEarningsCache (SQLite table earnings_cache, TTL = 7 days).
  PIT key: unique (ticker, year, quarter, fetched_date)

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.earnings_provider import EarningsProvider
from src.domain.value_objects.earnings_record import EarningsRecord
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_earnings_cache import StockbitEarningsCache
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

_EARNINGS_URL = STOCKBIT_CFG.earnings_url

_DEFAULT_QUARTERS = 4


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

    def __init__(
        self,
        api_client,
        db_path: Path | str = Path("data.db"),
    ) -> None:
        self._db_path = Path(db_path).expanduser()
        self._cache = StockbitEarningsCache(self._get_conn())
        super().__init__(api_client, db_path)

    def _ensure_schema(self) -> None:
        self._cache.ensure_schema()

    def is_cache_fresh(self, ticker: str) -> bool:
        """True when any earnings-history snapshot for this ticker is within TTL.

        The current calendar quarter is often not reported yet. Treating that
        missing period as stale causes repeated enrichment fetches that do not
        add usable rows. The refresh gate only needs to know whether the latest
        available earnings history was fetched recently.
        """
        return self._cache.is_fresh(ticker)

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
            return self._cache.read(ticker, as_of_date=as_of_date)[:quarters]

        # Check if current quarter is fresh — if so, serve fully from cache
        if self.is_cache_fresh(ticker):
            cached = self._cache.read(ticker)[:quarters]
            if cached:
                return cached

        # Fetch from API, walking backwards through prev_earnings_period
        fetched = self._fetch_quarters(ticker, quarters)
        if fetched:
            for record in fetched:
                self._cache.write_record(record)
            return fetched

        # API unavailable — fall back to whatever is cached
        return self._cache.read(ticker)[:quarters]

    def _fetch_quarters(self, ticker: str, quarters: int) -> list[EarningsRecord]:
        if self._api_client is None:
            return []

        records: list[EarningsRecord] = []
        current_q, current_y = _current_quarter_year()

        consecutive_failures = 0
        max_failures = 4  # Try up to 1 year back to find the first reported quarter

        while len(records) < quarters and consecutive_failures < max_failures:
            if self._cache.is_row_fresh(ticker, current_y, current_q):
                # Row already cached and fresh — load from cache and still get prev period pointer
                cached_row = self._cache.read_single(ticker, current_y, current_q)
                if cached_row:
                    records.append(cached_row)
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
                # Walk backward to find the latest reported quarter
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
