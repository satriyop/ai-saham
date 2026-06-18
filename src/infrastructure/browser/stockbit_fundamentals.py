"""
StockbitFundamentalsProvider — fundamental ratios from Stockbit KeyStats API.

Calls /keystats/ratio/v1/{ticker}?year_limit=10 and returns a CompanyFundamentals
object with key ratios extracted by name from the flat metric list.

Actual API shape (confirmed 2026-06-18, BBCA):
  data.closure_fin_items_results[].fin_name_results[].fitem.{name, value}
  name examples: "Return on Equity (TTM)", "Current PE Ratio (TTM)", ...
  value examples: "22.41%", "13.32", "5.00" (always strings, may include % and ,)

Caching: SQLite table `company_fundamentals` keyed by ticker with 7-day TTL.
ROE, Net Profit Margin, Piotroski F-Score, Revenue YoY Growth are quarterly metrics.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.value_objects.company_fundamentals import CompanyFundamentals

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_KEYSTATS_URL = "https://exodus.stockbit.com/keystats/ratio/v1/{ticker}?year_limit=10"

_CACHE_TTL_DAYS = 7

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
    near_52w_high_rank  REAL
)
"""


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

    return CompanyFundamentals(
        ticker=ticker.upper(),
        fetched_date=date.today(),
        pe_ratio_ttm=pe,
        roe_ttm=roe,
        net_profit_margin=npm,
        revenue_yoy_growth=rev_yoy,
        piotroski_f_score=f_score,
        dividend_yield=div_yld,
        week52_high=hi52,
        week52_low=lo52,
        near_52w_high_rank=near52,
    )


class StockbitFundamentalsProvider(FundamentalsProvider):
    """Fetches key fundamental ratios from Stockbit KeyStats API.

    SQLite cache with 7-day TTL — underlying metrics (ROE, NPM, F-score)
    are quarterly and change only at earnings releases.
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider",
        db_path: Path,
    ) -> None:
        self._provider = broker_provider
        self._db_path = db_path
        self._mem_cache: dict[str, CompanyFundamentals | None] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(_CREATE_TABLE)
        except Exception as e:
            logger.warning("company_fundamentals: failed to create cache table: %s", e)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists with fetched_date within the 7-day TTL window."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date FROM company_fundamentals WHERE ticker=? LIMIT 1",
                    (ticker.upper(),),
                ).fetchone()
            if not row:
                return False
            fetched = date.fromisoformat(row[0])
            return (date.today() - fetched).days <= _CACHE_TTL_DAYS
        except Exception:
            return False

    def get_fundamentals(self, ticker: str) -> CompanyFundamentals | None:
        key = ticker.upper()
        if key in self._mem_cache:
            return self._mem_cache[key]

        cached = self._read_cache(key)
        if cached is not None:
            self._mem_cache[key] = cached
            return cached

        result = self._fetch(key)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(self, ticker: str) -> CompanyFundamentals | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank "
                    "FROM company_fundamentals WHERE ticker=?",
                    (ticker,),
                ).fetchone()
            if not row:
                return None
            try:
                fetched = date.fromisoformat(row[0])
            except (ValueError, TypeError):
                return None
            if (date.today() - fetched).days > _CACHE_TTL_DAYS:
                return None
            f_score_raw = row[5]
            return CompanyFundamentals(
                ticker=ticker,
                fetched_date=fetched,
                pe_ratio_ttm=row[1],
                roe_ttm=row[2],
                net_profit_margin=row[3],
                revenue_yoy_growth=row[4],
                piotroski_f_score=int(f_score_raw) if f_score_raw is not None else None,
                dividend_yield=row[6],
                week52_high=row[7],
                week52_low=row[8],
                near_52w_high_rank=row[9],
            )
        except Exception as e:
            logger.warning("company_fundamentals: cache read failed for %s: %s", ticker, e)
            return None

    def _write_cache(self, fund: CompanyFundamentals) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO company_fundamentals "
                    "(ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fund.ticker,
                        fund.fetched_date.isoformat(),
                        fund.pe_ratio_ttm,
                        fund.roe_ttm,
                        fund.net_profit_margin,
                        fund.revenue_yoy_growth,
                        fund.piotroski_f_score,
                        fund.dividend_yield,
                        fund.week52_high,
                        fund.week52_low,
                        fund.near_52w_high_rank,
                    ),
                )
        except Exception as e:
            logger.warning("company_fundamentals: cache write failed for %s: %s", fund.ticker, e)

    def _fetch(self, ticker: str) -> CompanyFundamentals | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _KEYSTATS_URL.format(ticker=ticker)
            body = _exodus_get(url, token)
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
            return result
        except Exception as e:
            logger.warning("Fundamentals fetch failed for %s: %s", ticker, e)
            return None
