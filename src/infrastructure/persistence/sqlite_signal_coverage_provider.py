"""
SQLite implementation of SignalCoverageProvider.

Queries the enrichment cache tables to report per-factor row counts and
usable-data counts. Missing tables return zero rather than raising — a freshly
initialized DB is a valid state. Read-only, offline, deterministic.

Layer: Infrastructure — sqlite3 usage is expected and intentional here.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from src.application.ports.signal_coverage_provider import (
    FactorCoverage,
    SignalCoverageProvider,
    SignalCoverageReport,
)

logger = logging.getLogger(__name__)

# Per-factor: (factor_name, table, usable_where_predicate)
# usable_where is None when no reliable quality column exists; in that case
# usable_rows equals total_rows and FactorCoverage.note flags this as
# "cache total (no quality filter)".
_FACTOR_TABLES: tuple[tuple[str, str, str | None], ...] = (
    ("bandar_intensity", "bandar_detector", "broker_accdist IS NOT NULL"),
    ("foreign_flow_quality", "foreign_flow_points", None),
    ("insider_activity", "insider_cache", "shares > 0"),
    ("seasonality_edge", "seasonality_cache", None),
    ("analyst_consensus", "analyst_cache", "analyst_count > 0"),
    ("forward_valuation", "forward_estimates_cache", None),
    ("sector_metadata", "stock_meta", "sector IS NOT NULL"),
    ("company_profile", "company_profile_cache", "listing_board IS NOT NULL"),
    ("earnings_history", "earnings_cache", "eps_actual IS NOT NULL"),
)

_CACHE_TOTAL_NOTE = "cache total (no quality filter)"


class SqliteSignalCoverageProvider(SignalCoverageProvider):
    """Read per-factor enrichment coverage from the local SQLite cache DB."""

    def compute(self, db_path: Path) -> SignalCoverageReport:
        resolved = Path(db_path)
        factors: list[FactorCoverage] = []

        with sqlite3.connect(str(resolved)) as conn:
            total_tickers = _scalar(conn, "SELECT COUNT(DISTINCT ticker) FROM candles")
            for factor, table, usable_where in _FACTOR_TABLES:
                factors.append(_factor_coverage(conn, factor, table, usable_where))

        return SignalCoverageReport(
            db_path=str(resolved),
            as_of=_today(),
            total_tickers_in_db=total_tickers,
            factors=tuple(factors),
        )


def _factor_coverage(
    conn: sqlite3.Connection, factor: str, table: str, usable_where: str | None
) -> FactorCoverage:
    total_rows = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
    total_tickers = _scalar(conn, f"SELECT COUNT(DISTINCT ticker) FROM {table}")

    if usable_where is None:
        return FactorCoverage(
            factor=factor,
            total_rows=total_rows,
            usable_rows=total_rows,
            total_tickers=total_tickers,
            note=_CACHE_TOTAL_NOTE,
        )

    usable_rows = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {table} WHERE {usable_where}",
        fallback=total_rows,
    )
    return FactorCoverage(
        factor=factor,
        total_rows=total_rows,
        usable_rows=usable_rows,
        total_tickers=total_tickers,
    )


def _scalar(conn: sqlite3.Connection, query: str, fallback: int = 0) -> int:
    try:
        cursor = conn.execute(query)
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else fallback
    except sqlite3.Error as exc:
        logger.debug("signal coverage query failed (%s): %s", query, exc)
        return fallback


def _today() -> date:
    return date.today()
