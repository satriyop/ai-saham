"""
StockbitValuationProvider — per-ticker valuation metrics from Stockbit.

Calls /valuation/company/{ticker}/metrics and returns a ValuationMetrics object.

Actual API shape (confirmed 2026-06-20, BBCA):
  data: list of {id: int, value: str}
  id=0 entries are placeholders — filtered on ingest.
  Non-zero values observed for BBCA: {12635: 20.96, 13200: 471.10}

Known metric IDs (empirical, see ValuationMetrics.KNOWN_METRIC_LABELS):
  12635 → P/E (current)
  13200 → EPS TTM (IDR/share)
  12623 → +1σ PE (1-year band)
  12626 → +2σ PE (1-year band)

Caching: SQLite table `valuation_metrics_cache`, 1-day TTL.
  Primary key: ticker. Metrics stored as JSON blob.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.valuation_provider import ValuationProvider
from src.domain.value_objects.valuation_metrics import ValuationMetrics

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_VALUATION_URL = STOCKBIT_CFG.valuation_metrics_url

_TTL_DAYS = 1

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS valuation_metrics_cache (
    ticker       TEXT PRIMARY KEY,
    fetched_at   TEXT NOT NULL,
    metrics_json TEXT NOT NULL
)
"""


def _parse_response(ticker: str, body: dict) -> ValuationMetrics | None:
    """Parse /valuation/company/{ticker}/metrics response."""
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return None

    raw: dict[int, float] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        metric_id = entry.get("id")
        raw_val = entry.get("value")
        if not isinstance(metric_id, int) or metric_id == 0:
            continue
        try:
            val = float(raw_val) if raw_val is not None else 0.0
        except (ValueError, TypeError):
            continue
        if val != 0.0:
            raw[metric_id] = val

    if not raw:
        return None

    return ValuationMetrics(
        ticker=ticker.upper(),
        fetched_at=datetime.now(),
        raw=raw,
    )


class StockbitValuationProvider(ValuationProvider):
    """Fetches and caches per-ticker valuation metrics from the Stockbit Exodus API."""

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path | None = None,
    ) -> None:
        self._api_client = api_client
        self._db_path = db_path or Path("data/saham.db")
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._get_conn() as conn:
            conn.execute(_CREATE_TABLE)

    def is_cache_fresh(self, ticker: str) -> bool:
        cutoff = (datetime.now() - timedelta(days=_TTL_DAYS)).isoformat()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT fetched_at FROM valuation_metrics_cache WHERE ticker=? AND fetched_at>=?",
                (ticker.upper(), cutoff),
            ).fetchone()
        return row is not None

    def _read_cache(self, ticker: str) -> ValuationMetrics | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT fetched_at, metrics_json FROM valuation_metrics_cache WHERE ticker=?",
                (ticker.upper(),),
            ).fetchone()
        if row is None:
            return None
        try:
            raw_str = json.loads(row["metrics_json"])
            raw = {int(k): float(v) for k, v in raw_str.items()}
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        return ValuationMetrics(
            ticker=ticker.upper(),
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            raw=raw,
        )

    def _write_cache(self, metrics: ValuationMetrics) -> None:
        metrics_json = json.dumps({str(k): v for k, v in metrics.raw.items()})
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO valuation_metrics_cache "
                "(ticker, fetched_at, metrics_json) VALUES (?, ?, ?)",
                (metrics.ticker, metrics.fetched_at.isoformat(), metrics_json),
            )

    def get_valuation(self, ticker: str) -> ValuationMetrics | None:
        if self._api_client is None:
            return self._read_cache(ticker)

        if self.is_cache_fresh(ticker):
            return self._read_cache(ticker)

        key = ticker.upper()
        url = _VALUATION_URL.format(ticker=key)
        try:
            body = self._api_client.get(url)
        except Exception as exc:
            logger.debug("valuation fetch failed for %s: %s", key, exc)
            return self._read_cache(ticker)

        metrics = _parse_response(key, body or {})
        if metrics is not None:
            self._write_cache(metrics)
            return metrics

        return self._read_cache(ticker)
