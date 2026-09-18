"""Compose sidecar-first IEV capture-time lookup for pre-open session status.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository


class IevSessionCaptureLookup:
    """Prefer ``data/iev/YYYYMMDD/iev.json``; fall back to SQLite history."""

    def __init__(
        self,
        *,
        db_path: Path | str | None = None,
        sidecar_root: Path | str = Path("data/iev"),
    ) -> None:
        self._sidecar = IEVJsonSidecarWriter(sidecar_root)
        self._db_path = Path(db_path).expanduser() if db_path is not None else None

    def captured_at_for(self, session_date: date) -> datetime | None:
        captured = self._sidecar.read_captured_at(session_date)
        if captured is not None:
            return captured
        if self._db_path is None or not self._db_path.is_file():
            return None
        repo = SQLiteIEVRepository(self._db_path, initialize_schema=False)
        return repo.latest_collected_at(session_date)
