"""
SQLite cache for CompanyFundamentals — schema, TTL, PIT read, historical write.

Owns the company_fundamentals table and all cache-freshness, point-in-time, and
publication-lag logic. Pure cache — no API payload parsing, no network calls.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS company_fundamentals (
    ticker              TEXT NOT NULL,
    fetched_date        TEXT NOT NULL,
    pe_ratio_ttm        REAL,
    roe_ttm             REAL,
    net_profit_margin   REAL,
    revenue_yoy_growth  REAL,
    piotroski_f_score   INTEGER,
    dividend_yield      REAL,
    week52_high         REAL,
    week52_low          REAL,
    near_52w_high_rank  REAL,
    market_cap_idr      INTEGER,
    pbv                 REAL,
    UNIQUE(ticker, fetched_date)
)
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
]


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


class StockbitFundamentalsCache:
    """SQLite cache for CompanyFundamentals with TTL and PIT lookups."""

    def __init__(self, db_path: Path, *, cache_ttl_days: int) -> None:
        self._db_path = Path(db_path).expanduser()
        self._cache_ttl_days = cache_ttl_days

    def ensure_schema(self) -> None:
        try:
            SqliteMigrationRunner(self._db_path).run("company_fundamentals", _MIGRATIONS)
        except Exception as e:
            logger.warning("company_fundamentals: failed to create cache table: %s", e)

    def is_fresh(self, ticker: str) -> bool:
        """True if a row exists with fetched_date within the TTL window."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date FROM company_fundamentals "
                    "WHERE ticker=? ORDER BY date(fetched_date) DESC, fetched_date DESC LIMIT 1",
                    (ticker.upper(),),
                ).fetchone()
            if not row:
                return False
            fetched_at = _parse_fetched_at(row[0])
            return (
                fetched_at is not None
                and (datetime.now() - fetched_at).days <= self._cache_ttl_days
            )
        except Exception:
            return False

    def read(self, ticker: str, as_of_date: date | None = None) -> CompanyFundamentals | None:
        where = "WHERE ticker=?"
        params: tuple = (ticker,)
        if as_of_date is not None:
            where += " AND date(fetched_date) <= date(?)"
            params = (ticker, as_of_date.isoformat())
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv "
                    f"FROM company_fundamentals {where} "
                    "ORDER BY date(fetched_date) DESC, fetched_date DESC "
                    "LIMIT 1",
                    params,
                ).fetchone()
            if not row:
                return None
            fetched_at = _parse_fetched_at(row[0])
            if fetched_at is None:
                return None
            if as_of_date is None and (datetime.now() - fetched_at).days > self._cache_ttl_days:
                return None
            f_score_raw = row[5]
            return CompanyFundamentals(
                ticker=ticker,
                pe_ratio_ttm=row[1],
                roe_ttm=row[2],
                net_profit_margin=row[3],
                revenue_yoy_growth=row[4],
                piotroski_f_score=int(f_score_raw) if f_score_raw is not None else None,
                dividend_yield=row[6],
                week52_high=row[7],
                week52_low=row[8],
                near_52w_high_rank=row[9],
                market_cap_idr=int(row[10]) if row[10] is not None else None,
                pbv=float(row[11]) if row[11] is not None else None,
                fetched_at=fetched_at,
            )
        except Exception as e:
            logger.warning("company_fundamentals: cache read failed for %s: %s", ticker, e)
            return None

    def write(self, fund: CompanyFundamentals) -> None:
        fetched_str = fund.fetched_at.isoformat() if fund.fetched_at else datetime.now().isoformat()
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO company_fundamentals "
                    "(ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                    "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                    "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fund.ticker,
                        fetched_str,
                        fund.pe_ratio_ttm,
                        fund.roe_ttm,
                        fund.net_profit_margin,
                        fund.revenue_yoy_growth,
                        fund.piotroski_f_score,
                        fund.dividend_yield,
                        fund.week52_high,
                        fund.week52_low,
                        fund.near_52w_high_rank,
                        fund.market_cap_idr,
                        fund.pbv,
                    ),
                )
        except Exception as e:
            logger.warning("company_fundamentals: cache write failed for %s: %s", fund.ticker, e)

    def write_historical_rows(self, rows: list[CompanyFundamentals]) -> int:
        """Write historical quarterly rows to the PIT table with a 60-day publication lag.

        IDX companies publish quarterly reports within ~30 days of quarter end;
        60 days is a conservative upper bound. A Q1 2024 row (period_end March 31)
        is stored with fetched_date = "2024-05-30", so PIT reads only surface it
        for as_of_date >= 2024-05-30 -- after the report was realistically public.

        Rows where available_date is within the TTL window (or in the future)
        are skipped. Without this guard, a near-future fetched_date would make
        is_fresh() return True and suppress the live fetch entirely.

        Uses INSERT OR IGNORE so real snapshots (which carry piotroski_f_score,
        market_cap_idr, etc.) are never overwritten by these derived rows.
        """
        _LAG = timedelta(days=60)
        cutoff = date.today() - timedelta(days=self._cache_ttl_days)
        inserted = 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                for fund in rows:
                    if fund.fetched_at is None:
                        continue
                    available_date = fund.fetched_at.date() + _LAG
                    if available_date >= cutoff:
                        continue
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO company_fundamentals "
                        "(ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
                        "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
                        "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            fund.ticker,
                            available_date.isoformat(),
                            fund.pe_ratio_ttm,
                            fund.roe_ttm,
                            fund.net_profit_margin,
                            fund.revenue_yoy_growth,
                            fund.piotroski_f_score,
                            fund.dividend_yield,
                            fund.week52_high,
                            fund.week52_low,
                            fund.near_52w_high_rank,
                            fund.market_cap_idr,
                            fund.pbv,
                        ),
                    )
                    inserted += cursor.rowcount
        except Exception as e:
            logger.warning("company_fundamentals: historical write failed: %s", e)
        return inserted
