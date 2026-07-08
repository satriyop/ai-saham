"""
StockbitFundamentalsProvider — fundamental ratios from Stockbit KeyStats API.

Calls /keystats/ratio/v1/{ticker}?year_limit=10 and returns a CompanyFundamentals
object with key ratios extracted by name from the flat metric list.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.closure_fin_items_results[].fin_name_results[].fitem.{name, value}
  name examples: "Return on Equity (TTM)", "Current PE Ratio (TTM)", ...
  value examples: "22.41%", "13.32", "5.00" (always strings, may include % and ,)
  data.info.market_cap.raw → int IDR (e.g. 776634150000000)
  data.info.pbv.raw        → float (e.g. 3.0)

Caching: SQLite table `company_fundamentals` keyed by ticker with 7-day TTL.
ROE, Net Profit Margin, Piotroski F-Score, Revenue YoY Growth are quarterly metrics.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.value_objects.company_fundamentals import CompanyFundamentals

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_KEYSTATS_URL = STOCKBIT_CFG.keystats_url
_CACHE_TTL_DAYS = STOCKBIT_CFG.cache_ttl_days_fundamentals

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS company_fundamentals (
    ticker              TEXT PRIMARY KEY,
    fetched_date        TEXT NOT NULL,
    pe_ratio_ttm        REAL,
    roe_ttm             REAL,
    net_profit_margin   REAL,
    revenue_yoy_growth  REAL,
    piotroski_f_score   INTEGER,
    dividend_yield      REAL,
    week52_high         REAL,
    week52_low          REAL,
    near_52w_high_rank  REAL,
    market_cap_idr      INTEGER,
    pbv                 REAL
)
"""

_CREATE_TABLE_PIT = """
CREATE TABLE IF NOT EXISTS company_fundamentals_pit (
    ticker              TEXT NOT NULL,
    fetched_date        TEXT NOT NULL,
    pe_ratio_ttm        REAL,
    roe_ttm             REAL,
    net_profit_margin   REAL,
    revenue_yoy_growth  REAL,
    piotroski_f_score   INTEGER,
    dividend_yield      REAL,
    week52_high         REAL,
    week52_low          REAL,
    near_52w_high_rank  REAL,
    market_cap_idr      INTEGER,
    pbv                 REAL,
    UNIQUE(ticker, fetched_date)
)
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
    (1, "ALTER TABLE company_fundamentals ADD COLUMN market_cap_idr INTEGER"),
    (2, "ALTER TABLE company_fundamentals ADD COLUMN pbv REAL"),
    # Migrations 3-6: convert from single-row (ticker PRIMARY KEY) to multi-row
    # PIT table keyed by (ticker, fetched_date). Follows the same pattern as
    # analyst_cache migrations 4-8. Existing rows are preserved.
    (3, _CREATE_TABLE_PIT),
    (
        4,
        "INSERT OR IGNORE INTO company_fundamentals_pit "
        "SELECT ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
        "revenue_yoy_growth, piotroski_f_score, dividend_yield, week52_high, "
        "week52_low, near_52w_high_rank, market_cap_idr, pbv "
        "FROM company_fundamentals",
    ),
    (5, "DROP TABLE company_fundamentals"),
    (6, "ALTER TABLE company_fundamentals_pit RENAME TO company_fundamentals"),
    # Migration 7: separate table for derived historical fundamentals.
    # These rows are NOT used by PIT reads (get_fundamentals with as_of_date).
    # Quarter-end date ≠ publication date, so mixing them into the PIT table
    # would introduce look-ahead bias for as_of queries near the quarter end.
    (
        7,
        """CREATE TABLE IF NOT EXISTS company_fundamentals_history (
            ticker TEXT NOT NULL,
            period_end_date TEXT NOT NULL,
            period TEXT NOT NULL,
            year INTEGER NOT NULL,
            net_profit_margin REAL,
            revenue_yoy_growth REAL,
            UNIQUE(ticker, period_end_date)
        )""",
    ),
]


_QUARTER_END: dict[str, tuple[int, int]] = {
    "Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)
}


def _parse_financial_value(s: str | None) -> float | None:
    """Parse Stockbit formatted value like '14,684 B' or '29,654 B' → 14684.0.

    Units (B/T/M/K) are stripped — the caller uses the ratio, not the absolute
    value, so units only need to be consistent within a single response.
    """
    if not s or s.strip() in ("-", "N/A", ""):
        return None
    try:
        cleaned = s.strip().replace(",", "")
        # Strip unit suffix if present
        for suffix in (" B", " T", " M", " K", "B", "T", "M", "K"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                break
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _strip(raw: str | None) -> str:
    return (raw or "").strip().rstrip("%").replace(",", "")


def _parse_float(raw: str | None) -> float | None:
    try:
        v = _strip(raw)
        if not v or v in ("-", "N/A", ""):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_int(raw: str | None) -> int | None:
    f = _parse_float(raw)
    return int(round(f)) if f is not None else None


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


def _build_metrics(body: dict) -> dict[str, str]:
    """Flatten the nested fin_name_results list into a name → value dict."""
    metrics: dict[str, str] = {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return metrics
    for section in data.get("closure_fin_items_results") or []:
        for item in section.get("fin_name_results") or []:
            fitem = item.get("fitem") or {}
            name = fitem.get("name")
            value = fitem.get("value")
            if name and value is not None:
                metrics[name] = str(value)
    return metrics


def _parse_market_cap(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        cleaned = raw.replace(",", "").strip()
        multiplier = 1
        if cleaned.endswith("T"):
            multiplier = 1_000_000_000_000
            cleaned = cleaned[:-1].strip()
        elif cleaned.endswith("B"):
            multiplier = 1_000_000_000
            cleaned = cleaned[:-1].strip()
        elif cleaned.endswith("M"):
            multiplier = 1_000_000
            cleaned = cleaned[:-1].strip()
        val = float(cleaned)
        return int(round(val * multiplier))
    except (ValueError, TypeError):
        return None


def _parse_fundamentals(ticker: str, body: dict) -> CompanyFundamentals | None:
    metrics = _build_metrics(body)
    if not metrics:
        return None

    pe      = _parse_float(metrics.get("Current PE Ratio (TTM)"))
    roe     = _parse_float(metrics.get("Return on Equity (TTM)"))
    npm     = _parse_float(metrics.get("Net Profit Margin (Quarter)"))
    rev_yoy = _parse_float(metrics.get("Revenue (Quarter YoY Growth)"))
    f_score = _parse_int(metrics.get("Piotroski F-Score"))
    div_yld = _parse_float(metrics.get("Dividend Yield"))
    hi52    = _parse_float(metrics.get("52 Week High"))
    lo52    = _parse_float(metrics.get("52 Week Low"))
    near52  = _parse_float(metrics.get("Rank (Near 52 Weeks High)"))

    if all(v is None for v in [pe, roe, npm, rev_yoy, f_score]):
        return None

    data_raw = body.get("data") if isinstance(body, dict) else {}
    stats = (data_raw or {}).get("stats") or {}
    
    # 1. Parse market cap from stats.market_cap
    market_cap_idr: int | None = None
    if isinstance(stats, dict) and "market_cap" in stats:
        market_cap_idr = _parse_market_cap(stats["market_cap"])
    
    # 2. Parse PBV from flat metrics list, with fallback to legacy info
    pbv = _parse_float(metrics.get("Current Price to Book Value"))
    if pbv is None:
        info = (data_raw or {}).get("info") or {}
        if isinstance(info, dict):
            pbv_raw = (info.get("pbv") or {}).get("raw")
            try:
                pbv = float(pbv_raw) if pbv_raw is not None else None
            except (TypeError, ValueError):
                pass

    return CompanyFundamentals(
        ticker=ticker.upper(),
        pe_ratio_ttm=pe,
        roe_ttm=roe,
        net_profit_margin=npm,
        revenue_yoy_growth=rev_yoy,
        piotroski_f_score=f_score,
        dividend_yield=div_yld,
        week52_high=hi52,
        week52_low=lo52,
        near_52w_high_rank=near52,
        market_cap_idr=market_cap_idr,
        pbv=pbv,
        fetched_at=datetime.now(),
    )



def _parse_historical_rows(ticker: str, body: dict) -> list[CompanyFundamentals]:
    """Extract quarterly Net Income + Revenue history from financial_year_parent.

    Returns one CompanyFundamentals per (year, quarter) where both values are
    available. Only net_profit_margin and revenue_yoy_growth are populated;
    all other fields (market_cap_idr, piotroski_f_score, roe_ttm, etc.) are None.

    fetched_at is set to the quarter end date so PIT queries work correctly:
      Q1 → March 31, Q2 → June 30, Q3 → Sep 30, Q4 → Dec 31.
    """
    try:
        data = body.get("data") if isinstance(body, dict) else None
        fyp = (data or {}).get("financial_year_parent") or {}
        groups = fyp.get("financial_year_groups") or []
        if not groups:
            return []

        # Collect quarterly values keyed by (year, quarter)
        quarterly: dict[tuple[str, str], dict[str, float]] = {}
        for group in groups:
            fitem_name = group.get("fitem_name", "")
            if fitem_name not in ("Net Income", "Revenue"):
                continue
            col = "net_income" if fitem_name == "Net Income" else "revenue"
            for year_entry in group.get("financial_year_values") or []:
                year = str(year_entry.get("year") or "").strip()
                if not year:
                    continue
                for pv in year_entry.get("period_values") or []:
                    period = str(pv.get("period") or "").strip()
                    if period not in _QUARTER_END:
                        continue
                    val = _parse_financial_value(pv.get("quarter_value"))
                    if val is None:
                        continue
                    key = (year, period)
                    if key not in quarterly:
                        quarterly[key] = {}
                    quarterly[key][col] = val

        rows: list[CompanyFundamentals] = []
        for (year, period), vals in quarterly.items():
            net_income = vals.get("net_income")
            revenue = vals.get("revenue")
            if net_income is None or revenue is None or revenue == 0:
                continue

            npm: float | None = (net_income / revenue) * 100

            prior_year = str(int(year) - 1)
            prior = quarterly.get((prior_year, period), {})
            prior_rev = prior.get("revenue")
            rev_yoy: float | None = None
            if prior_rev and prior_rev != 0:
                rev_yoy = ((revenue - prior_rev) / abs(prior_rev)) * 100

            month, day = _QUARTER_END[period]
            try:
                fetched_at = datetime(int(year), month, day)
            except ValueError:
                continue

            rows.append(
                CompanyFundamentals(
                    ticker=ticker.upper(),
                    pe_ratio_ttm=None,
                    roe_ttm=None,
                    net_profit_margin=round(npm, 4),
                    revenue_yoy_growth=round(rev_yoy, 4) if rev_yoy is not None else None,
                    piotroski_f_score=None,
                    dividend_yield=None,
                    week52_high=None,
                    week52_low=None,
                    near_52w_high_rank=None,
                    market_cap_idr=None,
                    pbv=None,
                    fetched_at=fetched_at,
                )
            )
        return rows
    except Exception as exc:
        logger.debug("_parse_historical_rows failed for %s: %s", ticker, exc)
        return []


class StockbitFundamentalsProvider(FundamentalsProvider, StockbitCachingProvider):
    """Fetches key fundamental ratios from Stockbit KeyStats API.

    SQLite cache with 7-day TTL — underlying metrics (ROE, NPM, F-score)
    are quarterly and change only at earnings releases.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path,
    ) -> None:
        self._mem_cache: dict[str, CompanyFundamentals | None] = {}
        super().__init__(api_client, db_path)

    def _ensure_schema(self) -> None:
        try:
            SqliteMigrationRunner(self._db_path).run("company_fundamentals", _MIGRATIONS)
        except Exception as e:
            logger.warning("company_fundamentals: failed to create cache table: %s", e)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists with fetched_date within the 7-day TTL window."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date FROM company_fundamentals "
                    "WHERE ticker=? ORDER BY date(fetched_date) DESC, fetched_date DESC LIMIT 1",
                    (ticker.upper(),),
                ).fetchone()
            if not row:
                return False
            fetched_at = _parse_fetched_at(row[0])
            return fetched_at is not None and (datetime.now() - fetched_at).days <= _CACHE_TTL_DAYS
        except Exception:
            return False

    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> CompanyFundamentals | None:
        key = ticker.upper()
        # Bypass in-memory cache in backtest mode: same ticker may be valid at
        # one historical date but not another within a single backtest run.
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
    ) -> CompanyFundamentals | None:
        where = "WHERE ticker=?"
        params: tuple = (ticker,)
        if as_of_date is not None:
            # PIT mode: return the latest snapshot whose fetch date is on or before
            # as_of_date. Never fall back to a future row — that would introduce
            # look-ahead bias in historical replay.
            where += " AND date(fetched_date) <= date(?)"
            params = (ticker, as_of_date.isoformat())
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv "
                    f"FROM company_fundamentals {where} "
                    "ORDER BY date(fetched_date) DESC, fetched_date DESC "
                    "LIMIT 1",
                    params,
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if fetched_at is None:
                return None
            if as_of_date is None and (datetime.now() - fetched_at).days > _CACHE_TTL_DAYS:
                return None
            f_score_raw = row[5]
            return CompanyFundamentals(
                ticker=ticker,
                pe_ratio_ttm=row[1],
                roe_ttm=row[2],
                net_profit_margin=row[3],
                revenue_yoy_growth=row[4],
                piotroski_f_score=int(f_score_raw) if f_score_raw is not None else None,
                dividend_yield=row[6],
                week52_high=row[7],
                week52_low=row[8],
                near_52w_high_rank=row[9],
                market_cap_idr=int(row[10]) if row[10] is not None else None,
                pbv=float(row[11]) if row[11] is not None else None,
                fetched_at=fetched_at,
            )
        except Exception as e:
            logger.warning("company_fundamentals: cache read failed for %s: %s", ticker, e)
            return None

    def _write_cache(self, fund: CompanyFundamentals) -> None:
        fetched_str = fund.fetched_at.isoformat() if fund.fetched_at else datetime.now().isoformat()
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO company_fundamentals "
                    "(ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fund.ticker,
                        fetched_str,
                        fund.pe_ratio_ttm,
                        fund.roe_ttm,
                        fund.net_profit_margin,
                        fund.revenue_yoy_growth,
                        fund.piotroski_f_score,
                        fund.dividend_yield,
                        fund.week52_high,
                        fund.week52_low,
                        fund.near_52w_high_rank,
                        fund.market_cap_idr,
                        fund.pbv,
                    ),
                )
        except Exception as e:
            logger.warning("company_fundamentals: cache write failed for %s: %s", fund.ticker, e)

    def _write_historical_rows(self, rows: list[CompanyFundamentals]) -> int:
        """Write derived quarterly rows to company_fundamentals_history (not PIT table).

        Historical rows go to a separate table so get_fundamentals() PIT reads
        are never polluted with data whose availability date is unknown.
        Quarter-end date ≠ publication date — Q1 2024 results typically publish
        in April/May, not March 31, so storing them as PIT rows would introduce
        look-ahead bias for as_of queries in that window.
        """
        _month_to_period = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
        inserted = 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                for fund in rows:
                    if fund.fetched_at is None:
                        continue
                    period = _month_to_period.get(fund.fetched_at.month)
                    if period is None:
                        continue
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO company_fundamentals_history "
                        "(ticker, period_end_date, period, year, "
                        "net_profit_margin, revenue_yoy_growth) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            fund.ticker,
                            fund.fetched_at.strftime("%Y-%m-%d"),
                            period,
                            fund.fetched_at.year,
                            fund.net_profit_margin,
                            fund.revenue_yoy_growth,
                        ),
                    )
                    inserted += cursor.rowcount
        except Exception as e:
            logger.warning("company_fundamentals_history: write failed: %s", e)
        return inserted

    def _fetch(self, ticker: str) -> CompanyFundamentals | None:
        if self._api_client is None:
            return None
        try:
            url = _KEYSTATS_URL.format(ticker=ticker)
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty keystats response for %s", ticker)
                return None
            result = _parse_fundamentals(ticker, body)
            if result:
                logger.debug(
                    "Fundamentals %s → ROE=%.1f%% F=%s PE=%.1f",
                    ticker,
                    result.roe_ttm or 0,
                    result.piotroski_f_score,
                    result.pe_ratio_ttm or 0,
                )
            # Backfill historical quarterly rows from financial_year_parent.
            # Uses INSERT OR IGNORE so real snapshots are never overwritten.
            historical = _parse_historical_rows(ticker, body)
            if historical:
                written = self._write_historical_rows(historical)
                logger.debug(
                    "Fundamentals %s: backfilled %d/%d historical quarterly rows",
                    ticker, written, len(historical),
                )
            return result
        except Exception as e:
            logger.warning("Fundamentals fetch failed for %s: %s", ticker, e)
            return None
