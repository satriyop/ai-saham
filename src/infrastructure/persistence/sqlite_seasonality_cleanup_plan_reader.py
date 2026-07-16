"""
Read-only SQLite observer for the DQ-001G seasonality cleanup plan.

Opens SQLite in read-only URI mode and never executes write/DDL statements.
Returns raw, uninterpreted seasonality_cache rows only — row invalidity
policy lives in BuildSeasonalityCleanupPlanUseCase, not here.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from src.application.use_case.build_seasonality_cleanup_plan_use_case import (
    RawSeasonalityCacheObservation,
    RawSeasonalityCacheRow,
)

_TABLE = "seasonality_cache"
_SELECT_COLUMNS = (
    "ticker, year, month, fetched_month, fetched_at, source, "
    "avg_return_pct, win_rate_pct, positive_years, total_years, back_years"
)


class SQLiteSeasonalityCleanupPlanReader:
    """Read-only observer of raw seasonality_cache rows for the cleanup plan."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_seasonality_cache(self) -> RawSeasonalityCacheObservation:
        if not self._db_path.exists():
            return RawSeasonalityCacheObservation(exists=False)

        with closing(self._connect()) as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if _TABLE not in existing_tables:
                return RawSeasonalityCacheObservation(exists=False)

            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
                "ORDER BY ticker ASC, year ASC, month ASC, fetched_at ASC"
            ).fetchall()

        return RawSeasonalityCacheObservation(
            exists=True,
            rows=tuple(
                RawSeasonalityCacheRow(
                    ticker=row["ticker"],
                    year=row["year"],
                    month=row["month"],
                    fetched_month=row["fetched_month"],
                    fetched_at=row["fetched_at"],
                    source=row["source"],
                    avg_return_pct=row["avg_return_pct"],
                    win_rate_pct=row["win_rate_pct"],
                    positive_years=row["positive_years"],
                    total_years=row["total_years"],
                    back_years=row["back_years"],
                )
                for row in rows
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
