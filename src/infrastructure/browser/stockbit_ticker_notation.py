"""Stockbit ticker notation/status provider.

Calls /emitten/{ticker}/info and caches the display-only notation/status
context in SQLite with a daily TTL.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.ports.ticker_notation_repository import TickerNotationRepository
from src.domain.value_objects.ticker_notation import (
    TickerNotation,
    TickerNotationSnapshot,
)

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )
    from src.infrastructure.config.stockbit_config import StockbitConfig

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.config.stockbit_config import load_stockbit_config

logger = logging.getLogger(__name__)


def _parse_bool(raw) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _visible_catalog_names(data: dict) -> list[str]:
    names: list[str] = []
    for item in data.get("catalogs") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("catalog_name") or item.get("company_symbol")
        if name and item.get("show", True):
            names.append(str(name))
    return names


def _listing_board(data: dict) -> str | None:
    for item in data.get("catalogs") or []:
        if not isinstance(item, dict):
            continue
        if item.get("company_type") == "listing-board":
            name = item.get("catalog_name") or item.get("company_symbol")
            return str(name) if name else None
    return None


def _parse_notations(data: dict) -> list[TickerNotation]:
    parsed: list[TickerNotation] = []
    for item in data.get("notation") or data.get("notations") or []:
        if not isinstance(item, dict):
            continue
        code = item.get("notation_code") or item.get("code")
        desc = item.get("notation_desc") or item.get("description")
        if code:
            parsed.append(
                TickerNotation(
                    code=str(code).strip().upper(),
                    description=str(desc or "").strip(),
                )
            )
    return parsed


def _parse_snapshot(ticker: str, body: dict) -> TickerNotationSnapshot | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    market_hour = data.get("market_hour") or {}
    trading_limit = data.get("trading_limit_info") or {}
    corp_action = data.get("corp_action") or data.get("corpaction") or {}

    return TickerNotationSnapshot(
        ticker=ticker.upper(),
        status=data.get("status"),
        tradeable=_parse_bool(data.get("tradeable")),
        listing_board=_listing_board(data),
        sector=data.get("sector"),
        sub_sector=data.get("sub_sector"),
        haircut_percentage=trading_limit.get("haircut_percentage"),
        notations=_parse_notations(data),
        market_status=market_hour.get("status"),
        suspend_info=market_hour.get("suspend_info") or None,
        corp_action_active=_parse_bool(
            corp_action.get("active") if isinstance(corp_action, dict) else None
        ),
        has_uma=_parse_bool(data.get("has_uma") or data.get("uma")),
        catalogs=_visible_catalog_names(data),
        source="stockbit",
        fetched_at=datetime.now(),
    )


class StockbitTickerNotationProvider(
    TickerNotationProvider, TickerNotationRepository, StockbitCachingProvider
):
    """Fetches and caches Stockbit ticker notation/status context."""

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path | str = Path("data.db"),
        *,
        connection_provider: "StockbitSQLiteConnectionProvider | None" = None,
        stockbit_config: StockbitConfig | None = None,
    ) -> None:
        self._stockbit_config = stockbit_config or load_stockbit_config()
        super().__init__(api_client, db_path, connection_provider=connection_provider)

    def _ensure_schema(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticker_notation_cache (
                        ticker              TEXT NOT NULL,
                        status              TEXT,
                        tradeable           INTEGER,
                        listing_board       TEXT,
                        sector              TEXT,
                        sub_sector          TEXT,
                        haircut_percentage  TEXT,
                        notations_json      TEXT NOT NULL DEFAULT '[]',
                        market_status       TEXT,
                        suspend_info        TEXT,
                        corp_action_active  INTEGER,
                        has_uma             INTEGER,
                        catalogs_json       TEXT NOT NULL DEFAULT '[]',
                        source              TEXT NOT NULL DEFAULT 'stockbit',
                        fetched_date        TEXT NOT NULL,
                        fetched_at          TEXT NOT NULL
                    )
                """)
                _rebuild_ticker_notation_cache_if_needed(conn)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ticker_notation_fetched
                    ON ticker_notation_cache(ticker, fetched_date)
                """)
        except Exception as e:
            logger.warning("ticker_notation_cache schema error: %s", e)

    def is_cache_fresh(self, ticker: str) -> bool:
        today = date.today().isoformat()
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT 1 FROM ticker_notation_cache
                    WHERE ticker=? AND fetched_date=? LIMIT 1
                    """,
                    (ticker.upper(), today),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def get_notation(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        key = ticker.upper()
        if as_of_date is not None:
            return self._read_cache(key, as_of_date=as_of_date)
        if self.is_cache_fresh(key):
            return self._read_cache(key)
        if self._api_client is None:
            return self._read_cache(key)
        result = self._fetch(key)
        if result is not None:
            self.save_notation(result)
            return result
        return self._read_cache(key)

    def save_notation(self, snapshot: TickerNotationSnapshot) -> None:
        fetched_at = snapshot.fetched_at or datetime.now()
        fetched_date = fetched_at.date()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO ticker_notation_cache (
                        ticker, status, tradeable, listing_board, sector, sub_sector,
                        haircut_percentage, notations_json, market_status, suspend_info,
                        corp_action_active, has_uma, catalogs_json, source,
                        fetched_date, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.ticker.upper(),
                        snapshot.status,
                        _bool_to_int(snapshot.tradeable),
                        snapshot.listing_board,
                        snapshot.sector,
                        snapshot.sub_sector,
                        snapshot.haircut_percentage,
                        json.dumps([n.to_dict() for n in snapshot.notations]),
                        snapshot.market_status,
                        snapshot.suspend_info,
                        _bool_to_int(snapshot.corp_action_active),
                        _bool_to_int(snapshot.has_uma),
                        json.dumps(snapshot.catalogs),
                        snapshot.source,
                        fetched_date.isoformat(),
                        fetched_at.isoformat(),
                    ),
                )
        except Exception as e:
            logger.debug("ticker_notation_cache write error for %s: %s", snapshot.ticker, e)

    def read_cached(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        """Public cache-only read. Never fetches from network."""
        return self._read_cache(ticker, as_of_date=as_of_date)

    def _read_cache(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        where = "WHERE ticker=?"
        params: tuple[str, ...] = (ticker.upper(),)
        if as_of_date is not None:
            where += " AND date(fetched_date) <= date(?)"
            params = (ticker.upper(), as_of_date.isoformat())
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM ticker_notation_cache "
                    f"{where} "
                    "ORDER BY date(fetched_date) DESC, fetched_at DESC "
                    "LIMIT 1",
                    params,
                ).fetchone()
        except Exception as e:
            logger.debug("ticker_notation_cache read error for %s: %s", ticker, e)
            return None

        if row is None:
            return None

        try:
            notation_rows = json.loads(row["notations_json"] or "[]")
        except json.JSONDecodeError:
            notation_rows = []
        notations = [
            TickerNotation(
                code=str(item.get("code") or "").strip().upper(),
                description=str(item.get("description") or "").strip(),
            )
            for item in notation_rows
            if isinstance(item, dict) and item.get("code")
        ]

        try:
            catalogs = json.loads(row["catalogs_json"] or "[]")
        except json.JSONDecodeError:
            catalogs = []
        catalogs = [str(item) for item in catalogs if item]

        return TickerNotationSnapshot(
            ticker=row["ticker"],
            status=row["status"],
            tradeable=_int_to_bool(row["tradeable"]),
            listing_board=row["listing_board"],
            sector=row["sector"],
            sub_sector=row["sub_sector"],
            haircut_percentage=row["haircut_percentage"],
            notations=notations,
            market_status=row["market_status"],
            suspend_info=row["suspend_info"],
            corp_action_active=_int_to_bool(row["corp_action_active"]),
            has_uma=_int_to_bool(row["has_uma"]),
            catalogs=catalogs,
            source=row["source"],
            fetched_at=_parse_timestamp(row["fetched_at"]),
        )

    def _fetch(self, ticker: str) -> TickerNotationSnapshot | None:
        if self._api_client is None:
            return None
        body = self._api_client.get(
            self._stockbit_config.emitten_info_url.format(ticker=ticker.upper())
        )
        if not body:
            return None
        return _parse_snapshot(ticker, body)


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _rebuild_ticker_notation_cache_if_needed(sqlite_conn: sqlite3.Connection) -> None:
    rows = sqlite_conn.execute("PRAGMA table_info(ticker_notation_cache)").fetchall()
    ticker_pk = any(row[1] == "ticker" and int(row[5]) > 0 for row in rows)
    if not ticker_pk:
        return
    sqlite_conn.execute("ALTER TABLE ticker_notation_cache RENAME TO ticker_notation_cache_old")
    sqlite_conn.execute("""
        CREATE TABLE ticker_notation_cache (
            ticker              TEXT NOT NULL,
            status              TEXT,
            tradeable           INTEGER,
            listing_board       TEXT,
            sector              TEXT,
            sub_sector          TEXT,
            haircut_percentage  TEXT,
            notations_json      TEXT NOT NULL DEFAULT '[]',
            market_status       TEXT,
            suspend_info        TEXT,
            corp_action_active  INTEGER,
            has_uma             INTEGER,
            catalogs_json       TEXT NOT NULL DEFAULT '[]',
            source              TEXT NOT NULL DEFAULT 'stockbit',
            fetched_date        TEXT NOT NULL,
            fetched_at          TEXT NOT NULL
        )
    """)
    sqlite_conn.execute("""
        INSERT INTO ticker_notation_cache (
            ticker, status, tradeable, listing_board, sector, sub_sector,
            haircut_percentage, notations_json, market_status, suspend_info,
            corp_action_active, has_uma, catalogs_json, source, fetched_date,
            fetched_at
        )
        SELECT ticker, status, tradeable, listing_board, sector, sub_sector,
               haircut_percentage, notations_json, market_status, suspend_info,
               corp_action_active, has_uma, catalogs_json, source, fetched_date,
               fetched_at
        FROM ticker_notation_cache_old
    """)
    sqlite_conn.execute("DROP TABLE ticker_notation_cache_old")
