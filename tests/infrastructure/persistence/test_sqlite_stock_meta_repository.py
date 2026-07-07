from __future__ import annotations

from datetime import date, datetime

from src.domain.entities.stock_meta import StockMeta
from src.infrastructure.persistence.sqlite_stock_meta_repository import (
    SQLiteStockMetaRepository,
)


def test_stock_meta_get_returns_latest_live_snapshot(tmp_path):
    repo = SQLiteStockMetaRepository(tmp_path / "data.db")
    repo.save(_meta("BBCA", "Financials", datetime(2026, 6, 1, 9)))
    repo.save(_meta("BBCA", "Banks", datetime(2026, 6, 5, 9)))

    result = repo.get("BBCA")

    assert result is not None
    assert result.sector == "Banks"


def test_stock_meta_get_returns_latest_snapshot_on_or_before_as_of_date(tmp_path):
    repo = SQLiteStockMetaRepository(tmp_path / "data.db")
    repo.save(_meta("BBCA", "Financials", datetime(2026, 6, 1, 9)))
    repo.save(_meta("BBCA", "Banks", datetime(2026, 6, 5, 9)))
    repo.save(_meta("BBCA", "Holding", datetime(2026, 6, 10, 9)))

    result = repo.get("BBCA", as_of_date=date(2026, 6, 6))

    assert result is not None
    assert result.sector == "Banks"


def test_stock_meta_get_ignores_future_snapshot_for_as_of_date(tmp_path):
    repo = SQLiteStockMetaRepository(tmp_path / "data.db")
    repo.save(_meta("BBCA", "Holding", datetime(2026, 6, 10, 9)))

    result = repo.get("BBCA", as_of_date=date(2026, 6, 6))

    assert result is None


def _meta(
    ticker: str,
    sector: str,
    fetched_at: datetime,
) -> StockMeta:
    return StockMeta(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector=sector,
        sector_key=sector.lower(),
        industry="Banking",
        industry_key="banking",
        source="test",
        fetched_at=fetched_at,
        checksum=f"{sector.lower()}-checksum",
    )
