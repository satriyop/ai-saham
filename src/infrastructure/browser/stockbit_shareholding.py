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

Caching: SQLite table `shareholding_composition` with 7-day TTL.
Filings land quarterly; 7 days catches mid-quarter corrections without daily re-fetches.

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

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_COMPOSITION_URL = STOCKBIT_CFG.shareholding_url
_CACHE_TTL_DAYS = STOCKBIT_CFG.cache_ttl_days_shareholding

# All known category labels from Stockbit shareholding API
_ALL_CATEGORIES = {
    "Mutual Funds", "Pension Funds", "Exchange Traded Funds", "Insurance",
    "Bank", "Central Bank", "Sovereign Wealth Fund", "Hedge Fund",
    "Investment Advisors", "Investment Manager", "Financial Institutional",
    "Capital Market Inst.", "Private Bank", "Private Equity", "Trustee Bank",
    "State Owned Enterprises", "Government", "Securities Company",
    "Foundation", "Partnership", "Corporate", "State Owned Company",
    "Educational Institution", "Assoc/Social Org", "Firm",
    "CV / Limited Partnership", "Congregation", "Brokerage Firms",
    "Sole Proprietorship", "Diocese", "Conference", "Peer to Peer Lending",
    "Cooperatives", "Individual", "International Organization",
}

# Institutional subset — professional money
_INSTITUTION_LABELS = {
    "Mutual Funds", "Pension Funds", "Exchange Traded Funds", "Insurance",
    "Bank", "Central Bank", "Sovereign Wealth Fund", "Hedge Fund",
    "Investment Advisors", "Investment Manager", "Financial Institutional",
    "Capital Market Inst.", "Private Bank", "Private Equity", "Trustee Bank",
    "State Owned Enterprises", "Government", "State Owned Company",
    "Securities Company",
}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS shareholding_composition (
    ticker TEXT NOT NULL PRIMARY KEY,
    fetched_date TEXT NOT NULL,
    report_date TEXT,
    institution_pct REAL,
    individual_pct REAL,
    top_holder_name TEXT,
    top_holder_pct REAL,
    total_shares INTEGER,
    total_shares_formatted TEXT
)
"""

_MIGRATE_COLUMNS = [
    "ALTER TABLE shareholding_composition ADD COLUMN total_shares INTEGER",
    "ALTER TABLE shareholding_composition ADD COLUMN total_shares_formatted TEXT",
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


class StockbitShareholdingProvider(ShareholdingProvider):
    """Fetches shareholding composition from Stockbit Exodus API.

    SQLite cache with 7-day TTL — IDX shareholding filings land quarterly.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path,
    ) -> None:
        self._api_client = api_client
        self._db_path = db_path
        self._mem_cache: dict[str, ShareholdingComposition | None] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(_CREATE_TABLE)
                for col_sql in _MIGRATE_COLUMNS:
                    try:
                        conn.execute(col_sql)
                    except Exception:
                        pass  # column already exists
        except Exception as e:
            logger.warning("shareholding: failed to create cache table: %s", e)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists within the 7-day TTL window."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date FROM shareholding_composition WHERE ticker=?",
                    (ticker.upper(),),
                ).fetchone()
            if not row:
                return False
            fetched_at = _parse_fetched_at(row[0])
            return fetched_at is not None and (datetime.now() - fetched_at).days <= _CACHE_TTL_DAYS
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
        if cached is not None:
            if as_of_date is None:
                self._mem_cache[key] = cached
            return cached

        if as_of_date is not None:
            # In backtest mode never fetch live data — would introduce look-ahead.
            return None

        result = self._fetch(key)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(
        self, ticker: str, as_of_date: date | None = None
    ) -> ShareholdingComposition | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date, report_date, institution_pct, individual_pct, "
                    "top_holder_name, top_holder_pct, total_shares, total_shares_formatted "
                    "FROM shareholding_composition WHERE ticker=?",
                    (ticker,),
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if fetched_at is None:
                return None
            if as_of_date is not None:
                # Backtest guard: prefer report_date (the IDX filing date) as the
                # boundary — it is semantically more accurate than fetched_date.
                # Fall back to fetched_date when report_date is absent.
                row_report_date = _parse_date(row[1] or "")
                boundary_date = row_report_date or fetched_at.date()
                if boundary_date > as_of_date:
                    return None
            elif (datetime.now() - fetched_at).days > _CACHE_TTL_DAYS:
                return None
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
        fetched_str = (
            comp.fetched_at.isoformat() if comp.fetched_at else datetime.now().isoformat()
        )
        try:
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
        except Exception as e:
            logger.warning("shareholding: cache write failed for %s: %s", comp.ticker, e)

    def _fetch(self, ticker: str) -> ShareholdingComposition | None:
        if self._api_client is None:
            return None
        try:
            url = _COMPOSITION_URL.format(ticker=ticker)
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
