"""
StockbitBrokerDistributionProvider — cross-broker counterparty flow from Stockbit.

Fetches /order-trade/broker/distribution for a ticker and caches the result
in SQLite for the trading day (1-day TTL).

Confirmed response shape (live probe 2026-06-20):
  data.date_info                           → "YYYY-MM-DD"
  data.by_value.top_broker_buy[].detail.code       → broker code
  data.by_value.top_broker_buy[].detail.type       → "Asing" | "Lokal" | "Pemerintah"
  data.by_value.top_broker_buy[].detail.amount     → int IDR
  data.by_value.top_broker_buy[].distribute_to[].code   → counterparty broker code
  data.by_value.top_broker_buy[].distribute_to[].type   → counterparty type
  data.by_value.top_broker_buy[].distribute_to[].amount → int IDR
  (same structure for top_broker_sell)

Layer: Infrastructure
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.broker_distribution_provider import BrokerDistributionProvider
from src.domain.value_objects.broker_distribution import (
    BrokerCounterparty,
    BrokerDistributionEntry,
    BrokerDistributionSnapshot,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)

_TTL_DAYS = 1


def _parse_counterparties(raw: list) -> tuple[BrokerCounterparty, ...]:
    result = []
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        result.append(BrokerCounterparty(
            broker_code=code.upper(),
            broker_type=str(item.get("type") or "").strip(),
            amount_idr=int(item.get("amount") or 0),
        ))
    return tuple(sorted(result, key=lambda c: c.amount_idr, reverse=True))


def _parse_entries(raw_list: list) -> tuple[BrokerDistributionEntry, ...]:
    result = []
    for item in (raw_list or []):
        if not isinstance(item, dict):
            continue
        detail = item.get("detail") or {}
        code = str(detail.get("code") or "").strip()
        if not code:
            continue
        result.append(BrokerDistributionEntry(
            broker_code=code.upper(),
            broker_type=str(detail.get("type") or "").strip(),
            amount_idr=int(detail.get("amount") or 0),
            counterparties=_parse_counterparties(item.get("distribute_to") or []),
        ))
    return tuple(sorted(result, key=lambda e: e.amount_idr, reverse=True))


def _parse_response(ticker: str, body: dict) -> BrokerDistributionSnapshot | None:
    data = (body or {}).get("data")
    if not isinstance(data, dict):
        return None

    date_str = str(data.get("date_info") or "")[:10]
    try:
        trading_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        trading_date = date.today()

    by_value = data.get("by_value") or {}
    top_buyers = _parse_entries(by_value.get("top_broker_buy") or [])
    top_sellers = _parse_entries(by_value.get("top_broker_sell") or [])

    if not top_buyers and not top_sellers:
        return None

    return BrokerDistributionSnapshot(
        ticker=ticker.upper(),
        date=trading_date,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        fetched_at=datetime.now(),
    )


class StockbitBrokerDistributionProvider(BrokerDistributionProvider):
    """Fetches cross-broker distribution from Stockbit /order-trade/broker/distribution.

    Caches per (ticker, date) in SQLite table `broker_distribution_cache`.
    TTL is 1 trading day (refreshes each morning).

    Args:
        broker_provider: Authenticated Stockbit session for token access.
        db_path:         Path to SQLite database.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: str | Path = Path("data.db"),
    ) -> None:
        self._api_client = api_client
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS broker_distribution_cache (
                        ticker          TEXT NOT NULL,
                        trading_date    TEXT NOT NULL,
                        top_buyers_json TEXT NOT NULL,
                        top_sellers_json TEXT NOT NULL,
                        fetched_date    TEXT NOT NULL,
                        PRIMARY KEY (ticker, trading_date)
                    )
                """)
        except Exception as exc:
            logger.warning("broker_distribution_cache schema error: %s", exc)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def is_cache_fresh(self, ticker: str) -> bool:
        cutoff = (date.today() - timedelta(days=_TTL_DAYS)).isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM broker_distribution_cache "
                    "WHERE ticker=? AND fetched_date >= ? LIMIT 1",
                    (ticker.upper(), cutoff),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _write(self, snapshot: BrokerDistributionSnapshot) -> None:
        try:
            buyers_json = json.dumps([
                {
                    "code": e.broker_code, "type": e.broker_type, "amount": e.amount_idr,
                    "counterparties": [
                        {"code": c.broker_code, "type": c.broker_type, "amount": c.amount_idr}
                        for c in e.counterparties
                    ],
                }
                for e in snapshot.top_buyers
            ])
            sellers_json = json.dumps([
                {
                    "code": e.broker_code, "type": e.broker_type, "amount": e.amount_idr,
                    "counterparties": [
                        {"code": c.broker_code, "type": c.broker_type, "amount": c.amount_idr}
                        for c in e.counterparties
                    ],
                }
                for e in snapshot.top_sellers
            ])
            fetched_str = snapshot.fetched_at.isoformat() if snapshot.fetched_at else datetime.now().isoformat()
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO broker_distribution_cache
                        (ticker, trading_date, top_buyers_json, top_sellers_json, fetched_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snapshot.ticker, snapshot.date.isoformat(), buyers_json, sellers_json, fetched_str),
                )
        except Exception as exc:
            logger.debug("broker_distribution_cache write error for %s: %s", snapshot.ticker, exc)

    def _read_cache(self, ticker: str, trading_date: date | None) -> BrokerDistributionSnapshot | None:
        try:
            with self._get_conn() as conn:
                if trading_date:
                    row = conn.execute(
                        "SELECT * FROM broker_distribution_cache WHERE ticker=? AND trading_date=? LIMIT 1",
                        (ticker.upper(), trading_date.isoformat()),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM broker_distribution_cache WHERE ticker=? ORDER BY trading_date DESC LIMIT 1",
                        (ticker.upper(),),
                    ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        return self._deserialize(ticker, row)

    def _deserialize(self, ticker: str, row: sqlite3.Row) -> BrokerDistributionSnapshot | None:
        try:
            buyers = tuple(
                BrokerDistributionEntry(
                    broker_code=e["code"], broker_type=e["type"], amount_idr=e["amount"],
                    counterparties=tuple(
                        BrokerCounterparty(
                            broker_code=c["code"], broker_type=c["type"], amount_idr=c["amount"]
                        )
                        for c in e.get("counterparties", [])
                    ),
                )
                for e in json.loads(row["top_buyers_json"])
            )
            sellers = tuple(
                BrokerDistributionEntry(
                    broker_code=e["code"], broker_type=e["type"], amount_idr=e["amount"],
                    counterparties=tuple(
                        BrokerCounterparty(
                            broker_code=c["code"], broker_type=c["type"], amount_idr=c["amount"]
                        )
                        for c in e.get("counterparties", [])
                    ),
                )
                for e in json.loads(row["top_sellers_json"])
            )
            return BrokerDistributionSnapshot(
                ticker=ticker.upper(),
                date=date.fromisoformat(row["trading_date"]),
                top_buyers=buyers,
                top_sellers=sellers,
            )
        except Exception as exc:
            logger.debug("broker_distribution_cache deserialize error: %s", exc)
            return None

    # ── Port implementation ───────────────────────────────────────────────────

    def get_distribution(
        self,
        ticker: str,
        trading_date: date | None = None,
    ) -> BrokerDistributionSnapshot | None:
        ticker = ticker.upper()

        if self.is_cache_fresh(ticker):
            cached = self._read_cache(ticker, trading_date)
            if cached:
                return cached

        if self._api_client is not None:
            snapshot = self._fetch_live(ticker)
            if snapshot:
                self._write(snapshot)
                return snapshot

        return self._read_cache(ticker, trading_date)

    def _fetch_live(self, ticker: str) -> BrokerDistributionSnapshot | None:
        try:
            url = STOCKBIT_CFG.broker_distribution_url.format(ticker=ticker)
            body = self._api_client.get(url)
            if not body:
                return None
            return _parse_response(ticker, body)
        except Exception as exc:
            logger.debug("broker_distribution fetch failed for %s: %s", ticker, exc)
            return None
