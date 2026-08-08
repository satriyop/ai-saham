"""NCP lock-window coverage metrics (task 05 slice 2)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.infrastructure.persistence.sqlite_iev_repository import (
    IEVSnapshot,
    SQLiteIEVRepository,
)


def _repo(tmp_path: Path) -> SQLiteIEVRepository:
    return SQLiteIEVRepository(tmp_path / "iev.db")


def test_ncp_lock_window_coverage_distinguishes_lock_days_from_discovery(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    day_lock = date(2026, 8, 5)
    day_disc = date(2026, 8, 4)

    # Lock-window write
    repo.save_snapshot(
        day_lock,
        [
            IEVSnapshot(date=day_lock, ticker="BBCA", iev=100, rank=1, iep=1000),
            IEVSnapshot(date=day_lock, ticker="BBRI", iev=90, rank=2, iep=900),
        ],
        collected_at=datetime(2026, 8, 5, 8, 57, 0),
        collection_started_at=datetime(2026, 8, 5, 8, 56, 5),
    )
    # Pre-NCP discovery write
    repo.save_snapshot(
        day_disc,
        [IEVSnapshot(date=day_disc, ticker="TLKM", iev=80, rank=1, iep=800)],
        collected_at=datetime(2026, 8, 4, 8, 50, 0),
        collection_started_at=datetime(2026, 8, 4, 8, 50, 0),
    )

    report = repo.get_ncp_lock_window_coverage(recent_days=10)
    assert report["history_dates"] == 2
    assert report["ncp_dates"] == 1
    by_date = {d["date"]: d for d in report["days"]}
    assert by_date["2026-08-05"]["has_lock_batch"] is True
    assert by_date["2026-08-05"]["ncp_tickers"] == 2
    assert by_date["2026-08-04"]["has_lock_batch"] is False
    assert by_date["2026-08-04"]["ncp_tickers"] == 0
    assert report["recent_lock_batch_days"] == 1
