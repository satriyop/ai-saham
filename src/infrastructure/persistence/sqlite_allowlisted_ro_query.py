"""Cache-only allowlisted SELECT runner for ADR-065 ro_data_query."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AllowlistedRoQueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class SqliteAllowlistedRoQuery:
    """Read-only SQLite executor for fixed prepared SQL shapes (no free SQL)."""

    def __init__(
        self, db_path: Path | str, *, max_rows: int = 50, busy_timeout_ms: int = 2_000
    ) -> None:
        self._db_path = Path(db_path)
        self._max_rows = max_rows
        self._busy_timeout_ms = busy_timeout_ms

    @property
    def db_path(self) -> Path:
        return self._db_path

    def is_available(self) -> bool:
        return self._db_path.is_file()

    def execute(
        self,
        sql: str,
        params: dict[str, Any],
    ) -> AllowlistedRoQueryResult:
        with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            cur = conn.execute(sql, params)
            colnames = tuple(d[0] for d in (cur.description or ()))
            raw_rows = cur.fetchmany(self._max_rows)
        rows = tuple(tuple("" if c is None else str(c) for c in row) for row in raw_rows)
        return AllowlistedRoQueryResult(columns=colnames, rows=rows)
