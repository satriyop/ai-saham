"""
StockbitBandarDetectorProvider — bandar detector signal from Stockbit Exodus API.

Calls /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET
      &market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL
      &limit=25&period=BROKER_SUMMARY_PERIOD_LATEST

Actual API shape (confirmed 2026-06-18, BBCA):
  data.bandar_detector.broker_accdist       → "Acc" | "Dis" | "Neutral"
  data.bandar_detector.avg.accdist          → today's intensity label
  data.bandar_detector.avg5.accdist         → 5-session intensity label
  data.bandar_detector.top1.accdist         → top operator's label
  data.bandar_detector.top1.percent         → float — concentration %
  data.bandar_detector.avg.percent          → float — avg net % of total volume
  data.bandar_detector.total_buyer          → int
  data.bandar_detector.total_seller         → int

Caching: SQLite table `bandar_detector` keyed by (ticker, session_date).
Data is fixed after each trading session closes — no TTL needed; simply check
if a row exists for today's date before hitting the API.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_MARKET_DETECTOR_URL = (
    "https://exodus.stockbit.com/marketdetectors/{ticker}"
    "?transaction_type=TRANSACTION_TYPE_NET"
    "&market_board=MARKET_BOARD_REGULER"
    "&investor_type=INVESTOR_TYPE_ALL"
    "&limit=25"
    "&period=BROKER_SUMMARY_PERIOD_LATEST"
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bandar_detector (
    ticker           TEXT NOT NULL,
    session_date     TEXT NOT NULL,
    broker_accdist   TEXT,
    today_accdist    TEXT,
    five_day_accdist TEXT,
    top1_accdist     TEXT,
    top1_percent     REAL,
    today_percent    REAL,
    total_buyer      INTEGER,
    total_seller     INTEGER,
    PRIMARY KEY (ticker, session_date)
)
"""


def _sub(d: dict | None, key: str) -> dict:
    """Safe nested access for bandar_detector sub-dicts."""
    return (d or {}).get(key) or {}


def _parse_snapshot(ticker: str, session_date: date, body: dict) -> BandarDetectorSnapshot | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    bd = data.get("bandar_detector")
    if not isinstance(bd, dict):
        return None

    broker_accdist = str(bd.get("broker_accdist") or "Neutral").strip()
    today_accdist = str(_sub(bd, "avg").get("accdist") or "Neutral").strip()
    five_day_accdist = str(_sub(bd, "avg5").get("accdist") or "Neutral").strip()
    top1_accdist = str(_sub(bd, "top1").get("accdist") or "Neutral").strip()

    try:
        top1_percent = float(_sub(bd, "top1").get("percent") or 0)
    except (TypeError, ValueError):
        top1_percent = 0.0

    try:
        today_percent = float(_sub(bd, "avg").get("percent") or 0)
    except (TypeError, ValueError):
        today_percent = 0.0

    try:
        total_buyer = int(bd.get("total_buyer") or 0)
    except (TypeError, ValueError):
        total_buyer = 0

    try:
        total_seller = int(bd.get("total_seller") or 0)
    except (TypeError, ValueError):
        total_seller = 0

    return BandarDetectorSnapshot(
        ticker=ticker.upper(),
        session_date=session_date,
        broker_accdist=broker_accdist,
        today_accdist=today_accdist,
        five_day_accdist=five_day_accdist,
        top1_accdist=top1_accdist,
        top1_percent=round(top1_percent, 4),
        today_percent=round(today_percent, 4),
        total_buyer=total_buyer,
        total_seller=total_seller,
    )


class StockbitBandarDetectorProvider(BandarDetectorProvider):
    """Fetches bandar detector signal from Stockbit Exodus API.

    SQLite cache keyed by (ticker, session_date) — data is fixed after
    market close, so one fetch per ticker per day is sufficient.
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider",
        db_path: Path,
    ) -> None:
        self._provider = broker_provider
        self._db_path = db_path
        self._mem_cache: dict[tuple[str, str], BandarDetectorSnapshot | None] = {}
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(_CREATE_TABLE)
        except Exception as e:
            logger.warning("bandar_detector: failed to create cache table: %s", e)

    def get_snapshot(
        self, ticker: str, session_date: date | None = None
    ) -> BandarDetectorSnapshot | None:
        target_date = session_date or date.today()
        key = (ticker.upper(), target_date.isoformat())

        if key in self._mem_cache:
            return self._mem_cache[key]

        cached = self._read_cache(ticker.upper(), target_date)
        if cached is not None:
            self._mem_cache[key] = cached
            return cached

        result = self._fetch(ticker.upper(), target_date)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(self, ticker: str, target_date: date) -> BandarDetectorSnapshot | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT broker_accdist, today_accdist, five_day_accdist, top1_accdist, "
                    "top1_percent, today_percent, total_buyer, total_seller "
                    "FROM bandar_detector WHERE ticker=? AND session_date=?",
                    (ticker, target_date.isoformat()),
                ).fetchone()
            if not row:
                return None
            return BandarDetectorSnapshot(
                ticker=ticker,
                session_date=target_date,
                broker_accdist=str(row[0] or "Neutral"),
                today_accdist=str(row[1] or "Neutral"),
                five_day_accdist=str(row[2] or "Neutral"),
                top1_accdist=str(row[3] or "Neutral"),
                top1_percent=float(row[4] or 0),
                today_percent=float(row[5] or 0),
                total_buyer=int(row[6] or 0),
                total_seller=int(row[7] or 0),
            )
        except Exception as e:
            logger.warning("bandar_detector: cache read failed for %s: %s", ticker, e)
            return None

    def _write_cache(self, snap: BandarDetectorSnapshot) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO bandar_detector "
                    "(ticker, session_date, broker_accdist, today_accdist, five_day_accdist, "
                    "top1_accdist, top1_percent, today_percent, total_buyer, total_seller) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        snap.ticker,
                        snap.session_date.isoformat(),
                        snap.broker_accdist,
                        snap.today_accdist,
                        snap.five_day_accdist,
                        snap.top1_accdist,
                        snap.top1_percent,
                        snap.today_percent,
                        snap.total_buyer,
                        snap.total_seller,
                    ),
                )
        except Exception as e:
            logger.warning("bandar_detector: cache write failed for %s: %s", snap.ticker, e)

    def _fetch(self, ticker: str, session_date: date) -> BandarDetectorSnapshot | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _MARKET_DETECTOR_URL.format(ticker=ticker)
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty bandar detector response for %s", ticker)
                return None
            result = _parse_snapshot(ticker, session_date, body)
            if result:
                logger.debug(
                    "BandarDetector %s → %s (score=%d)",
                    ticker,
                    result.broker_accdist,
                    result.accumulation_score,
                )
            return result
        except Exception as e:
            logger.warning("Bandar detector fetch failed for %s: %s", ticker, e)
            return None
