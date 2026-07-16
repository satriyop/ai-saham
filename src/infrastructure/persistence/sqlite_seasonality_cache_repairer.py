"""
SQLite implementation of SeasonalityCacheRepairer for DQ-001H.

Manages the seasonality_cache_quarantine table and performs transactional
quarantine+delete of invalid seasonality_cache rows.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.use_case.repair_seasonality_cache_use_case import (
        SeasonalityCacheRepairRow,
    )

_QUARANTINE_TABLE = "seasonality_cache_quarantine"

_CREATE_QUARANTINE_TABLE = """
CREATE TABLE IF NOT EXISTS seasonality_cache_quarantine (
    ticker                TEXT NOT NULL,
    year                  INTEGER NOT NULL,
    month                 INTEGER NOT NULL,
    fetched_month         TEXT,
    fetched_at            TEXT,
    source                TEXT,
    avg_return_pct        REAL,
    win_rate_pct          REAL,
    positive_years        INTEGER,
    total_years           INTEGER,
    back_years            INTEGER,
    quarantine_reasons_json TEXT NOT NULL,
    quarantined_at        TEXT NOT NULL,
    repair_run_id         TEXT NOT NULL,
    original_table        TEXT NOT NULL DEFAULT 'seasonality_cache',
    schema_version        INTEGER NOT NULL DEFAULT 1
)
"""

_INSERT_QUARANTINE_SQL = f"""
INSERT INTO {_QUARANTINE_TABLE}
    (ticker, year, month, fetched_month, fetched_at, source,
     avg_return_pct, win_rate_pct, positive_years, total_years, back_years,
     quarantine_reasons_json, quarantined_at, repair_run_id,
     original_table, schema_version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Column names used to identify a unique row for deletion.
_DELETE_IDENTITY_COLUMNS = [
    "ticker",
    "year",
    "month",
    "fetched_month",
    "fetched_at",
    "source",
    "avg_return_pct",
    "win_rate_pct",
    "positive_years",
    "total_years",
    "back_years",
]


def _build_delete_params(row: "SeasonalityCacheRepairRow") -> tuple[str, list]:
    """Build a parameterised DELETE statement that handles NULLs correctly.

    Each NULL column uses `col IS NULL` (no bound parameter);
    each non-NULL column uses `col = ?` with the value bound.
    """
    conditions: list[str] = []
    params: list = []
    for col in _DELETE_IDENTITY_COLUMNS:
        val = getattr(row, col)
        if val is None:
            conditions.append(f"{col} IS NULL")
        else:
            conditions.append(f"{col} = ?")
            params.append(val)
    sql = f"DELETE FROM seasonality_cache WHERE {' AND '.join(conditions)}"
    return sql, params


class SQLiteSeasonalityCacheRepairer:
    """SQLite repairer that quarantines invalid seasonality_cache rows."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_quarantine_table(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_QUARANTINE_TABLE)
            conn.commit()

    def quarantine_and_delete(
        self,
        rows: list["SeasonalityCacheRepairRow"],
        repair_run_id: str,
    ) -> int:
        """Transactionally insert into quarantine and delete from seasonality_cache.

        Returns the number of rows affected on success.
        Raises on failure after rolling back.
        """
        quarantined_at = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            for row in rows:
                reasons_json = json.dumps(list(row.reasons))
                conn.execute(
                    _INSERT_QUARANTINE_SQL,
                    (
                        row.ticker,
                        row.year,
                        row.month,
                        row.fetched_month,
                        row.fetched_at,
                        row.source,
                        row.avg_return_pct,
                        row.win_rate_pct,
                        row.positive_years,
                        row.total_years,
                        row.back_years,
                        reasons_json,
                        quarantined_at,
                        repair_run_id,
                        "seasonality_cache",
                        1,
                    ),
                )
                delete_sql, delete_params = _build_delete_params(row)
                cursor = conn.execute(delete_sql, delete_params)
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to delete 1 row for "
                        f"{row.ticker}/{row.year}/{row.month} "
                        f"but deleted {cursor.rowcount}. Rolling back."
                    )
            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
