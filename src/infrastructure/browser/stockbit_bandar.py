"""
StockbitBandarDetectorProvider — bandar detector signal from Stockbit Exodus API.

Calls /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET
      &market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL
      &limit=25&period=BROKER_SUMMARY_PERIOD_LATEST

Actual API shape (confirmed 2026-06-20, BBCA):
  data.bandar_detector.broker_accdist       → "Acc" | "Dis" | "Neutral"
  data.bandar_detector.avg.accdist          → today's intensity label
  data.bandar_detector.avg5.accdist         → 5-session intensity label
  data.bandar_detector.top1.accdist         → top operator's label (+ .percent)
  data.bandar_detector.top3.accdist         → top-3 brokers smoothed signal
  data.bandar_detector.top5.accdist         → top-5 brokers smoothed signal
  data.bandar_detector.top10.accdist        → top-10 brokers smoothed signal
  data.bandar_detector.number_broker_buysell → int (negative = more sellers)
  data.bandar_detector.average              → float VWAP
  data.bandar_detector.value                → int total traded value (IDR)
  data.bandar_detector.volume               → int total traded volume (lots)
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
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_MARKET_DETECTOR_URL = STOCKBIT_CFG.bandar_detector_url

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bandar_detector (
    ticker                TEXT NOT NULL,
    session_date          TEXT NOT NULL,
    broker_accdist        TEXT,
    today_accdist         TEXT,
    five_day_accdist      TEXT,
    top1_accdist          TEXT,
    top1_percent          REAL,
    today_percent         REAL,
    total_buyer           INTEGER,
    total_seller          INTEGER,
    top3_accdist          TEXT,
    top5_accdist          TEXT,
    top10_accdist         TEXT,
    number_broker_buysell INTEGER,
    vwap                  REAL,
    total_value           REAL,
    total_volume          INTEGER,
    PRIMARY KEY (ticker, session_date)
)
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
    (1, "ALTER TABLE bandar_detector ADD COLUMN top3_accdist TEXT"),
    (2, "ALTER TABLE bandar_detector ADD COLUMN top5_accdist TEXT"),
    (3, "ALTER TABLE bandar_detector ADD COLUMN top10_accdist TEXT"),
    (4, "ALTER TABLE bandar_detector ADD COLUMN number_broker_buysell INTEGER"),
    (5, "ALTER TABLE bandar_detector ADD COLUMN vwap REAL"),
    (6, "ALTER TABLE bandar_detector ADD COLUMN total_value REAL"),
    (7, "ALTER TABLE bandar_detector ADD COLUMN total_volume INTEGER"),
]


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
    top3_accdist = str(_sub(bd, "top3").get("accdist") or "").strip() or None
    top5_accdist = str(_sub(bd, "top5").get("accdist") or "").strip() or None
    top10_accdist = str(_sub(bd, "top10").get("accdist") or "").strip() or None

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

    try:
        number_broker_buysell = int(bd.get("number_broker_buysell") or 0)
    except (TypeError, ValueError):
        number_broker_buysell = None

    try:
        _vwap_raw = bd.get("average")
        vwap = Decimal(str(_vwap_raw)) if _vwap_raw else None
    except Exception:
        vwap = None

    try:
        _val_raw = bd.get("value")
        total_value = Decimal(str(_val_raw)) if _val_raw else None
    except Exception:
        total_value = None

    try:
        total_volume = int(bd.get("volume") or 0) or None
    except (TypeError, ValueError):
        total_volume = None

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
        top3_accdist=top3_accdist,
        top5_accdist=top5_accdist,
        top10_accdist=top10_accdist,
        number_broker_buysell=number_broker_buysell,
        vwap=vwap,
        total_value=total_value,
        total_volume=total_volume,
    )


class StockbitBandarDetectorProvider(BandarDetectorProvider, StockbitCachingProvider):
    """Fetches bandar detector signal from Stockbit Exodus API.

    SQLite cache keyed by (ticker, session_date) — data is fixed after
    market close, so one fetch per ticker per day is sufficient.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path,
    ) -> None:
        self._mem_cache: dict[tuple[str, str], BandarDetectorSnapshot | None] = {}
        super().__init__(api_client, db_path)

    def _ensure_schema(self) -> None:
        try:
            SqliteMigrationRunner(self._db_path).run("bandar_detector", _MIGRATIONS)
        except Exception as e:
            logger.warning("bandar_detector: failed to create cache table: %s", e)

    def _is_cache_fresh(self, ticker: str) -> bool:
        """True if a row exists for today's date (data is fixed after session close)."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM bandar_detector WHERE ticker=? AND session_date=? LIMIT 1",
                    (ticker.upper(), date.today().isoformat()),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def get_snapshot(
        self, ticker: str, session_date: date | None = None
    ) -> BandarDetectorSnapshot | None:
        target_date = session_date or date.today()
        key = (ticker.upper(), target_date.isoformat())

        if key in self._mem_cache:
            return self._mem_cache[key]

        cached = self._read_cache(
            ticker.upper(),
            target_date,
            allow_previous=self._api_client is None,
        )
        if cached is not None:
            self._mem_cache[key] = cached
            return cached

        result = self._fetch(ticker.upper(), target_date)
        self._mem_cache[key] = result
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(
        self,
        ticker: str,
        target_date: date,
        allow_previous: bool = False,
    ) -> BandarDetectorSnapshot | None:
        try:
            date_filter = "session_date<=?" if allow_previous else "session_date=?"
            order_clause = "ORDER BY session_date DESC " if allow_previous else ""
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT session_date, broker_accdist, today_accdist, five_day_accdist, top1_accdist, "
                    "top1_percent, today_percent, total_buyer, total_seller, "
                    "top3_accdist, top5_accdist, top10_accdist, "
                    "number_broker_buysell, vwap, total_value, total_volume "
                    f"FROM bandar_detector WHERE ticker=? AND {date_filter} "
                    f"{order_clause}LIMIT 1",
                    (ticker, target_date.isoformat()),
                ).fetchone()
            if not row:
                return None
            session_date = date.fromisoformat(str(row[0]))
            return BandarDetectorSnapshot(
                ticker=ticker,
                session_date=session_date,
                broker_accdist=str(row[1] or "Neutral"),
                today_accdist=str(row[2] or "Neutral"),
                five_day_accdist=str(row[3] or "Neutral"),
                top1_accdist=str(row[4] or "Neutral"),
                top1_percent=float(row[5] or 0),
                today_percent=float(row[6] or 0),
                total_buyer=int(row[7] or 0),
                total_seller=int(row[8] or 0),
                top3_accdist=str(row[9]) if row[9] else None,
                top5_accdist=str(row[10]) if row[10] else None,
                top10_accdist=str(row[11]) if row[11] else None,
                number_broker_buysell=int(row[12]) if row[12] is not None else None,
                vwap=Decimal(str(row[13])) if row[13] is not None else None,
                total_value=Decimal(str(row[14])) if row[14] is not None else None,
                total_volume=int(row[15]) if row[15] is not None else None,
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
                    "top1_accdist, top1_percent, today_percent, total_buyer, total_seller, "
                    "top3_accdist, top5_accdist, top10_accdist, "
                    "number_broker_buysell, vwap, total_value, total_volume) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                        snap.top3_accdist,
                        snap.top5_accdist,
                        snap.top10_accdist,
                        snap.number_broker_buysell,
                        float(snap.vwap) if snap.vwap is not None else None,
                        float(snap.total_value) if snap.total_value is not None else None,
                        snap.total_volume,
                    ),
                )
        except Exception as e:
            logger.warning("bandar_detector: cache write failed for %s: %s", snap.ticker, e)

    def _fetch(self, ticker: str, session_date: date) -> BandarDetectorSnapshot | None:
        if self._api_client is None:
            return None
        try:
            url = _MARKET_DETECTOR_URL.format(ticker=ticker)
            body = self._api_client.get(url)
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
