"""
SQLite implementation of StockMetaRepository.

Table: stock_meta
  ticker       TEXT PRIMARY KEY
  name         TEXT
  sector       TEXT
  sector_key   TEXT
  industry     TEXT
  industry_key TEXT
  source       TEXT
  fetched_at   TEXT   -- ISO datetime
  checksum     TEXT   -- sha1(sector|industry)[:12]

Layer: Infrastructure
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from src.domain.entities.stock_meta import StockMeta
from src.domain.ports.stock_meta_repository import StockMetaRepository

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS stock_meta (
    ticker       TEXT PRIMARY KEY,
    name         TEXT,
    sector       TEXT,
    sector_key   TEXT,
    industry     TEXT,
    industry_key TEXT,
    source       TEXT NOT NULL DEFAULT 'yahoo',
    fetched_at   TEXT NOT NULL,
    checksum     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_meta_sector   ON stock_meta(sector);
CREATE INDEX IF NOT EXISTS idx_stock_meta_industry ON stock_meta(industry);
"""


class SQLiteStockMetaRepository(StockMetaRepository):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLE)

    def get(self, ticker: str) -> StockMeta | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stock_meta WHERE ticker = ?", (ticker.upper(),)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entity(row)

    def save(self, meta: StockMeta) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stock_meta
                    (ticker, name, sector, sector_key, industry, industry_key, source, fetched_at, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name         = excluded.name,
                    sector       = excluded.sector,
                    sector_key   = excluded.sector_key,
                    industry     = excluded.industry,
                    industry_key = excluded.industry_key,
                    source       = excluded.source,
                    fetched_at   = excluded.fetched_at,
                    checksum     = excluded.checksum
                """,
                (
                    meta.ticker,
                    meta.name,
                    meta.sector,
                    meta.sector_key,
                    meta.industry,
                    meta.industry_key,
                    meta.source,
                    meta.fetched_at.isoformat(),
                    meta.checksum,
                ),
            )

    def needs_refresh(self, ticker: str, ttl_days: int) -> bool:
        """True when ticker is missing or fetched_at is older than ttl_days.
        Tickers with source='manual' are never refreshed automatically."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM stock_meta
                WHERE ticker = ?
                  AND (
                      source = 'manual'
                      OR fetched_at >= datetime('now', ? || ' days')
                  )
                """,
                (ticker.upper(), f"-{ttl_days}"),
            ).fetchone()
        return row is None  # None → missing or stale → needs refresh

    def cached_age_days(self, ticker: str) -> int | None:
        """Return how many days ago this ticker was last fetched, or None."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT CAST(
                    (julianday('now') - julianday(fetched_at)) AS INTEGER
                ) AS age_days
                FROM stock_meta WHERE ticker = ?
                """,
                (ticker.upper(),),
            ).fetchone()
        return int(row["age_days"]) if row else None

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> StockMeta:
        return StockMeta(
            ticker=row["ticker"],
            name=row["name"],
            sector=row["sector"],
            sector_key=row["sector_key"],
            industry=row["industry"],
            industry_key=row["industry_key"],
            source=row["source"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            checksum=row["checksum"],
        )
