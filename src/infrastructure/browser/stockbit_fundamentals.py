"""
StockbitFundamentalsProvider — fundamental ratios from Stockbit KeyStats API.

Calls /keystats/ratio/v1/{ticker}?year_limit=10 and returns a CompanyFundamentals
object with key ratios extracted by name from the flat metric list.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.closure_fin_items_results[].fin_name_results[].fitem.{name, value}
  name examples: "Return on Equity (TTM)", "Current PE Ratio (TTM)", ...
  value examples: "22.41%", "13.32", "5.00" (always strings, may include % and ,)
  data.info.market_cap.raw -> int IDR (e.g. 776634150000000)
  data.info.pbv.raw        -> float (e.g. 3.0)

Parsing is delegated to stockbit_fundamentals_parser.
Caching is delegated to stockbit_fundamentals_cache.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.value_objects.company_fundamentals import CompanyFundamentals

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_fundamentals_cache import StockbitFundamentalsCache
from src.infrastructure.browser.stockbit_fundamentals_parser import (
    _parse_fundamentals,
    _parse_historical_rows,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

_KEYSTATS_URL = STOCKBIT_CFG.keystats_url


class StockbitFundamentalsProvider(FundamentalsProvider, StockbitCachingProvider):
    """Fetches key fundamental ratios from Stockbit KeyStats API.

    SQLite cache with 7-day TTL -- underlying metrics (ROE, NPM, F-score)
    are quarterly and change only at earnings releases.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path,
    ) -> None:
        self._mem_cache: dict[str, CompanyFundamentals | None] = {}
        self._cache = StockbitFundamentalsCache(db_path)
        super().__init__(api_client, db_path)

    def _ensure_schema(self) -> None:
        self._cache.ensure_schema()

    def _is_cache_fresh(self, ticker: str) -> bool:
        return self._cache.is_fresh(ticker)

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
            # In backtest mode never fetch live data -- would introduce look-ahead.
            return None

        result = self._fetch(key)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(
        self, ticker: str, as_of_date: date | None = None
    ) -> CompanyFundamentals | None:
        return self._cache.read(ticker, as_of_date=as_of_date)

    def _write_cache(self, fund: CompanyFundamentals) -> None:
        self._cache.write(fund)

    def _write_historical_rows(self, rows: list[CompanyFundamentals]) -> int:
        return self._cache.write_historical_rows(rows)

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
                    "Fundamentals %s -> ROE=%.1f%% F=%s PE=%.1f",
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
