"""
StockbitShareholdingProvider — shareholding composition from Stockbit.

Calls /insider/shareholding/composition/companies/{ticker} and returns
a ShareholdingComposition object with aggregated institution/individual/top-holder data.

Actual API shape (confirmed 2026-06):
  data.periods[0].report_date                    → "2026-05-29"
  data.periods[0].total_shares.raw               → "123275050000" (string, total issued shares)
  data.periods[0].total_shares.formatted         → "123.28 B"
  data.periods[0].compositions[]                 → list of {label, percentage.raw, ...}

Category labels fall into two kinds:
  - Named entities (controlling shareholders, e.g. "DWIMURIA INVESTAMA ANDALAN")
  - Category holders (e.g. "Mutual Funds", "Individual", "Pension Funds", ...)

Aggregation:
  institution_pct  = sum of all labels in _INSTITUTION_LABELS
  individual_pct   = "Individual" label value
  top_holder_name  = named entity (not in _ALL_CATEGORIES) with highest %

Caching: SQLite table `shareholding_composition`.

Ownership composition is long-lived (IDX filings ~quarterly). Policy:

- **Display / ``read_cached``:** always return the latest stored row (no hide-by-TTL).
- **Refresh / ``_is_cache_fresh``:** TTL (config ``cache_ttl_days.shareholding``) only
  decides when ``fetch market`` enrichment should re-hit Stockbit — not whether
  the dashboard may show the last known composition.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.value_objects.shareholding_composition import ShareholdingComposition
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_pit_cache import (
    has_fresh_ticker_row,
    safe_cache_write,
    safe_schema_update,
)
from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )

logger = logging.getLogger(__name__)

# All known category labels from Stockbit shareholding API
_ALL_CATEGORIES = {
    "Mutual Funds",
    "Pension Funds",
    "Exchange Traded Funds",
    "Insurance",
    "Bank",
    "Central Bank",
    "Sovereign Wealth Fund",
    "Hedge Fund",
    "Investment Advisors",
    "Investment Manager",
    "Financial Institutional",
    "Capital Market Inst.",
    "Private Bank",
    "Private Equity",
    "Trustee Bank",
    "State Owned Enterprises",
    "Government",
    "Securities Company",
    "Foundation",
    "Partnership",
    "Corporate",
    "State Owned Company",
    "Educational Institution",
    "Assoc/Social Org",
    "Firm",
    "CV / Limited Partnership",
    "Congregation",
    "Brokerage Firms",
    "Sole Proprietorship",
    "Diocese",
    "Conference",
    "Peer to Peer Lending",
    "Cooperatives",
    "Individual",
    "International Organization",
}

# Institutional subset — professional money
_INSTITUTION_LABELS = {
    "Mutual Funds",
    "Pension Funds",
    "Exchange Traded Funds",
    "Insurance",
    "Bank",
    "Central Bank",
    "Sovereign Wealth Fund",
    "Hedge Fund",
    "Investment Advisors",
    "Investment Manager",
    "Financial Institutional",
    "Capital Market Inst.",
    "Private Bank",
    "Private Equity",
    "Trustee Bank",
    "State Owned Enterprises",
    "Government",
    "State Owned Company",
    "Securities Company",
}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS shareholding_composition (
    ticker TEXT NOT NULL,
    fetched_date TEXT NOT NULL,
    report_date TEXT,
    institution_pct REAL,
    individual_pct REAL,
    top_holder_name TEXT,
    top_holder_pct REAL,
    total_shares INTEGER,
    total_shares_formatted TEXT,
    UNIQUE(ticker, fetched_date)
)
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
]


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


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


def _parse_composition(ticker: str, body: dict) -> ShareholdingComposition | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    periods = data.get("periods")
    if not isinstance(periods, list) or not periods:
        return None

    period = periods[0]
    report_date = _parse_date(str(period.get("report_date") or ""))
    compositions = period.get("compositions") or []
    if not isinstance(compositions, list):
        return None

    total_shares: int | None = None
    total_shares_formatted: str | None = None
    ts = period.get("total_shares") or {}
    if isinstance(ts, dict):
        ts_raw = ts.get("raw")
        try:
            total_shares = int(str(ts_raw).replace(",", "")) if ts_raw is not None else None
        except (ValueError, TypeError):
            pass
        total_shares_formatted = str(ts.get("formatted") or "") or None

    institution_pct = 0.0
    individual_pct = 0.0
    top_holder_name = ""
    top_holder_pct = 0.0

    for item in compositions:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        pct = float((item.get("percentage") or {}).get("raw") or 0)

        if label in _INSTITUTION_LABELS:
            institution_pct += pct
        elif label == "Individual":
            individual_pct = pct
        elif label not in _ALL_CATEGORIES and pct > top_holder_pct:
            # Named entity (controlling shareholder)
            top_holder_name = label
            top_holder_pct = pct

    return ShareholdingComposition(
        ticker=ticker.upper(),
        report_date=report_date,
        institution_pct=round(institution_pct, 2),
        individual_pct=round(individual_pct, 2),
        top_holder_name=top_holder_name,
        top_holder_pct=round(top_holder_pct, 2),
        total_shares=total_shares,
        total_shares_formatted=total_shares_formatted,
        fetched_at=datetime.now(),
    )


class StockbitShareholdingProvider(ShareholdingProvider, StockbitCachingProvider):
    """Fetches shareholding composition from Stockbit Exodus API.

    Long-term ownership facts (quarterly filings). Latest cache row is always
    readable; TTL only gates live re-fetch when an API client is present.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path,
        *,
        connection_provider: "StockbitSQLiteConnectionProvider | None" = None,
        stockbit_config: StockbitConfig | None = None,
    ) -> None:
        self._stockbit_config = stockbit_config or load_stockbit_config()
        self._mem_cache: dict[str, ShareholdingComposition | None] = {}
        super().__init__(api_client, db_path, connection_provider=connection_provider)

    def _ensure_schema(self) -> None:
        def _update():
            SqliteMigrationRunner(self._db_path).run("shareholding_composition", _MIGRATIONS)

        safe_schema_update(logger=logger, label="shareholding_composition", update=_update)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists within the configured *refresh* TTL window."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                return has_fresh_ticker_row(
                    conn,
                    table="shareholding_composition",
                    ticker=ticker,
                    ttl_days=self._stockbit_config.cache_ttl_days_shareholding,
                )
        except Exception:
            return False

    def get_composition(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> ShareholdingComposition | None:
        key = ticker.upper()
        # Bypass in-memory cache in backtest mode: report_date gates on historical
        # filing availability, which varies per as_of_date.
        if as_of_date is None and key in self._mem_cache:
            return self._mem_cache[key]

        cached = self._read_cache(key, as_of_date=as_of_date)

        if as_of_date is not None:
            # Backtest / PIT: never fetch live (look-ahead).
            return cached

        # Live: re-fetch only when refresh TTL expired and network is available.
        if cached is not None and self._is_cache_fresh(key):
            self._mem_cache[key] = cached
            return cached

        if self._api_client is None:
            # Cache-only surfaces (view ticker): show last known composition.
            if cached is not None:
                self._mem_cache[key] = cached
            return cached

        result = self._fetch(key)
        if result is not None:
            self._write_cache(result)
            self._mem_cache[key] = result
            return result

        # Network miss: keep serving last known ownership rather than blanking UI.
        if cached is not None:
            self._mem_cache[key] = cached
        return cached

    def read_cached(
        self, ticker: str, as_of_date: date | None = None
    ) -> ShareholdingComposition | None:
        """Public cache-only read. Never fetches; never hides by refresh TTL."""
        return self._read_cache(ticker, as_of_date=as_of_date)

    def _read_cache(
        self, ticker: str, as_of_date: date | None = None
    ) -> ShareholdingComposition | None:
        where = "WHERE ticker=?"
        params: tuple = (ticker,)
        if as_of_date is not None:
            # PIT mode: use report_date (IDX quarterly filing date) as the primary
            # boundary because it is when the data became publicly available.
            # Fall back to fetched_date when report_date is absent.
            # Never fall back to a future row — look-ahead bias in historical replay.
            where += " AND COALESCE(date(report_date), date(fetched_date)) <= date(?)"
            params = (ticker, as_of_date.isoformat())
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date, report_date, institution_pct, individual_pct, "
                    "top_holder_name, top_holder_pct, total_shares, total_shares_formatted "
                    "FROM shareholding_composition "
                    f"{where} "
                    "ORDER BY COALESCE(date(report_date), date(fetched_date)) DESC, "
                    "fetched_date DESC "
                    "LIMIT 1",
                    params,
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if fetched_at is None:
                return None
            # Live + PIT: always surface the selected row. Refresh TTL is not a
            # display gate (ownership is long-term / quarterly).
            return ShareholdingComposition(
                ticker=ticker,
                report_date=_parse_date(row[1] or ""),
                institution_pct=float(row[2] or 0),
                individual_pct=float(row[3] or 0),
                top_holder_name=str(row[4] or ""),
                top_holder_pct=float(row[5] or 0),
                total_shares=int(row[6]) if row[6] is not None else None,
                total_shares_formatted=row[7],
                fetched_at=fetched_at,
            )
        except Exception as e:
            logger.warning("shareholding: cache read failed for %s: %s", ticker, e)
            return None

    def _write_cache(self, comp: ShareholdingComposition) -> None:
        fetched_str = comp.fetched_at.isoformat() if comp.fetched_at else datetime.now().isoformat()

        def _do_write():
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO shareholding_composition "
                    "(ticker, fetched_date, report_date, institution_pct, individual_pct, "
                    "top_holder_name, top_holder_pct, total_shares, total_shares_formatted) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        comp.ticker,
                        fetched_str,
                        comp.report_date.isoformat() if comp.report_date else None,
                        comp.institution_pct,
                        comp.individual_pct,
                        comp.top_holder_name,
                        comp.top_holder_pct,
                        comp.total_shares,
                        comp.total_shares_formatted,
                    ),
                )

        safe_cache_write(
            logger=logger,
            label="shareholding_composition",
            ticker=comp.ticker,
            write=_do_write,
        )

    def _fetch(self, ticker: str) -> ShareholdingComposition | None:
        if self._api_client is None:
            return None
        try:
            url = self._stockbit_config.shareholding_url.format(ticker=ticker)
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty shareholding response for %s", ticker)
                return None
            result = _parse_composition(ticker, body)
            if result:
                logger.debug("Shareholding %s → %s", ticker, result.label)
            return result
        except Exception as e:
            logger.warning("Shareholding fetch failed for %s: %s", ticker, e)
            return None
