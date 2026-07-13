"""
StockbitCompanyProfileProvider — company profile from Stockbit /emitten/{ticker}/profile.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.background                    → str (company description, Indonesian)
  data.history.board                 → "Papan Utama" | "Papan Pengembangan" | ...
  data.history.date                  → "31 May 2000" (IPO date, locale string)
  data.history.price                 → "1,400" (IDR, comma-formatted string)
  data.history.amount                → "927 B" (IPO proceeds with suffix)
  data.address[0].website            → "www.bca.co.id"
  data.address[0].email[]            → ["investor_relations@bca.co.id", ...]
  data.address[0].office             → office address string

Caching: SQLite table `company_profile_cache`, TTL = 30 days.
Profile data changes rarely (IPO date never; address occasionally).

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time

from src.domain.ports.company_profile_provider import CompanyProfileProvider
from src.domain.value_objects.company_profile import CompanyProfile
from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_pit_cache import (
    fetched_at_is_fresh,
    fetched_date_as_of_filter,
    latest_fetched_order,
    safe_cache_read,
    safe_cache_write,
    safe_schema_update,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

_PROFILE_URL = STOCKBIT_CFG.company_profile_url
_CACHE_TTL_DAYS = STOCKBIT_CFG.cache_ttl_days_company_profile

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS company_profile_cache (
    ticker          TEXT NOT NULL,
    fetched_date    TEXT NOT NULL,
    background      TEXT,
    listing_board   TEXT,
    ipo_date        TEXT,
    ipo_price       INTEGER,
    ipo_amount      TEXT,
    website         TEXT,
    email           TEXT,
    office_address  TEXT,
    UNIQUE(ticker, fetched_date)
)
"""


def _parse_profile(ticker: str, body: dict) -> CompanyProfile | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    background = str(data.get("background") or "") or None

    history = data.get("history") or {}
    listing_board = str(history.get("board") or "") or None
    ipo_date = str(history.get("date") or "") or None
    ipo_price: int | None = None
    raw_price = str(history.get("price") or "").replace(",", "").strip()
    try:
        ipo_price = int(raw_price) if raw_price else None
    except (ValueError, TypeError):
        pass
    ipo_amount = str(history.get("amount") or "") or None

    address_list = data.get("address") or []
    addr = address_list[0] if isinstance(address_list, list) and address_list else {}
    website = str(addr.get("website") or "") or None
    emails = addr.get("email") or []
    email = str(emails[0]) if isinstance(emails, list) and emails else None
    office_address = str(addr.get("office") or "") or None

    return CompanyProfile(
        ticker=ticker.upper(),
        background=background,
        listing_board=listing_board,
        ipo_date=ipo_date,
        ipo_price=ipo_price,
        ipo_amount=ipo_amount,
        website=website,
        email=email,
        office_address=office_address,
        fetched_at=datetime.now(),
    )


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


class StockbitCompanyProfileProvider(CompanyProfileProvider, StockbitCachingProvider):
    """Fetches company profile from Stockbit /emitten/{ticker}/profile.

    SQLite cache with 30-day TTL — profile data (IPO history, contacts) changes rarely.
    """

    def _ensure_schema(self) -> None:
        def _update():
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(_CREATE_TABLE)
                _rebuild_company_profile_cache_if_needed(conn)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_company_profile_ticker_fetched "
                    "ON company_profile_cache(ticker, fetched_date)"
                )

        safe_schema_update(logger=logger, label="company_profile_cache", update=_update)

    def get_profile(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> CompanyProfile | None:
        ticker = ticker.upper()
        if as_of_date is not None:
            return self._read_cache(ticker, as_of_date=as_of_date, require_fresh=False)
        cached = self._read_cache(ticker)
        if cached is not None:
            return cached
        result = self._fetch(ticker)
        if result is not None:
            self._write_cache(result)
        return result

    def _read_cache(
        self,
        ticker: str,
        as_of_date: date | None = None,
        require_fresh: bool = True,
    ) -> CompanyProfile | None:
        where = "WHERE ticker=?"
        params: tuple[str, ...] = (ticker,)
        frag, extra_params = fetched_date_as_of_filter(as_of_date)
        where += frag
        params += extra_params

        def _do_read():
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT fetched_date, background, listing_board, ipo_date, ipo_price, "
                    "ipo_amount, website, email, office_address "
                    f"FROM company_profile_cache {where} "
                    f"{latest_fetched_order()} LIMIT 1",
                    params,
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if require_fresh and not fetched_at_is_fresh(fetched_at, ttl_days=_CACHE_TTL_DAYS):
                return None
            return CompanyProfile(
                ticker=ticker,
                background=row[1],
                listing_board=row[2],
                ipo_date=row[3],
                ipo_price=int(row[4]) if row[4] is not None else None,
                ipo_amount=row[5],
                website=row[6],
                email=row[7],
                office_address=row[8],
                fetched_at=fetched_at,
            )

        return safe_cache_read(
            logger=logger,
            label="company_profile_cache",
            ticker=ticker,
            default=None,
            read=_do_read,
        )

    def _write_cache(self, profile: CompanyProfile) -> None:
        now = datetime.now()
        fetched_str = profile.fetched_at.isoformat() if profile.fetched_at else now.isoformat()

        def _do_write():
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO company_profile_cache "
                    "(ticker, fetched_date, background, listing_board, ipo_date, ipo_price, "
                    "ipo_amount, website, email, office_address) VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(ticker, fetched_date) DO UPDATE SET "
                    "background=excluded.background, "
                    "listing_board=excluded.listing_board, "
                    "ipo_date=excluded.ipo_date, "
                    "ipo_price=excluded.ipo_price, "
                    "ipo_amount=excluded.ipo_amount, "
                    "website=excluded.website, "
                    "email=excluded.email, "
                    "office_address=excluded.office_address",
                    (
                        profile.ticker,
                        fetched_str,
                        profile.background,
                        profile.listing_board,
                        profile.ipo_date,
                        profile.ipo_price,
                        profile.ipo_amount,
                        profile.website,
                        profile.email,
                        profile.office_address,
                    ),
                )

        safe_cache_write(
            logger=logger,
            label="company_profile_cache",
            ticker=profile.ticker,
            write=_do_write,
        )

    def _fetch(self, ticker: str) -> CompanyProfile | None:
        if self._api_client is None:
            return None
        try:
            url = _PROFILE_URL.format(ticker=ticker)
            body = self._api_client.get(url)
            if not body:
                logger.debug("Empty profile response for %s", ticker)
                return None
            result = _parse_profile(ticker, body)
            if result:
                logger.debug(
                    "CompanyProfile %s → board=%s IPO=%s",
                    ticker,
                    result.listing_board,
                    result.ipo_date,
                )
            return result
        except Exception as e:
            logger.warning("Company profile fetch failed for %s: %s", ticker, e)
            return None


def _rebuild_company_profile_cache_if_needed(sqlite_conn: sqlite3.Connection) -> None:
    rows = sqlite_conn.execute("PRAGMA table_info(company_profile_cache)").fetchall()
    ticker_pk = any(row[1] == "ticker" and int(row[5]) > 0 for row in rows)
    if not ticker_pk:
        return
    sqlite_conn.execute("ALTER TABLE company_profile_cache RENAME TO company_profile_cache_old")
    sqlite_conn.execute(_CREATE_TABLE)
    sqlite_conn.execute(
        """
        INSERT INTO company_profile_cache
            (ticker, fetched_date, background, listing_board, ipo_date, ipo_price,
             ipo_amount, website, email, office_address)
        SELECT ticker, fetched_date, background, listing_board, ipo_date, ipo_price,
               ipo_amount, website, email, office_address
        FROM company_profile_cache_old
        """
    )
    sqlite_conn.execute("DROP TABLE company_profile_cache_old")
