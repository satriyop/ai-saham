"""
Shared PIT cache primitives for Stockbit providers.

Small infrastructure-only helpers for SQLite point-in-time cache operations.
No domain imports, no provider-specific constants, no network calls.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import date, datetime, time
from typing import TypeVar

T = TypeVar("T")


def fetched_date_as_of_filter(
    as_of_date: date | None,
    *,
    column: str = "fetched_date",
) -> tuple[str, tuple[str, ...]]:
    if as_of_date is None:
        return "", ()
    return (
        " AND date(substr({},1,10)) <= date(?)".format(column),
        (as_of_date.isoformat(),),
    )


def latest_fetched_order(*, column: str = "fetched_date") -> str:
    return "ORDER BY date(substr({},1,10)) DESC, {} DESC".format(column, column)


def fetched_at_is_fresh(
    fetched_at: datetime | None,
    *,
    ttl_days: int,
    today: date | None = None,
) -> bool:
    if fetched_at is None:
        return False
    _today = today if today is not None else date.today()
    return (_today - fetched_at.date()).days <= ttl_days


def has_fresh_ticker_row(
    conn: sqlite3.Connection,
    *,
    table: str,
    ticker: str,
    ttl_days: int,
    fetched_column: str = "fetched_date",
) -> bool:
    row = conn.execute(
        "SELECT {} FROM {} "
        "WHERE ticker=? "
        "ORDER BY date(substr({},1,10)) DESC, {} DESC "
        "LIMIT 1".format(fetched_column, table, fetched_column, fetched_column),
        (ticker.upper(),),
    ).fetchone()
    if row is None:
        return False
    fetched_at = _parse_fetched_at(row[0])
    return fetched_at_is_fresh(fetched_at, ttl_days=ttl_days)


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


def safe_cache_read(
    *,
    logger: logging.Logger,
    label: str,
    ticker: str,
    default: T,
    read: Callable[[], T],
) -> T:
    try:
        return read()
    except Exception as e:
        logger.debug("%s read failed for %s: %s", label, ticker, e)
        return default


def safe_cache_write(
    *,
    logger: logging.Logger,
    label: str,
    ticker: str,
    write: Callable[[], None],
) -> None:
    try:
        write()
    except Exception as e:
        logger.debug("%s write failed for %s: %s", label, ticker, e)


def safe_schema_update(
    *,
    logger: logging.Logger,
    label: str,
    update: Callable[[], None],
) -> None:
    try:
        update()
    except Exception as e:
        logger.warning("%s schema error: %s", label, e)
