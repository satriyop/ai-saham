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

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_EMITTEN_INFO_URL = STOCKBIT_CFG.emitten_info_url


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


class StockbitTickerNotationProvider(TickerNotationProvider, TickerNotationRepository):
    """Fetches and caches Stockbit ticker notation/status context."""

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: str | Path = Path("data.db"),
    ) -> None:
        self._api_client = api_client
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticker_notation_cache (
                        ticker              TEXT PRIMARY KEY,
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
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ticker_notation_fetched
                    ON ticker_notation_cache(ticker, fetched_date)
                """)
        except Exception as e:
            logger.warning("ticker_notation_cache schema error: %s", e)

    def is_cache_fresh(self, ticker: str) -> bool:
        today = date.today().isoformat()
        try:
            with self._connect() as conn:
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

    def get_notation(self, ticker: str) -> TickerNotationSnapshot | None:
        key = ticker.upper()
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
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ticker_notation_cache (
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

    def _read_cache(self, ticker: str) -> TickerNotationSnapshot | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM ticker_notation_cache WHERE ticker=?",
                    (ticker.upper(),),
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
        body = self._api_client.get(_EMITTEN_INFO_URL.format(ticker=ticker.upper()))
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
