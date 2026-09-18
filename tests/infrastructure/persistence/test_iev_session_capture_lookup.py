"""Sidecar-first IEV capture-time lookup for pre-open session status."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
from src.infrastructure.persistence.iev_session_capture_lookup import (
    IevSessionCaptureLookup,
)
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)


def test_lookup_prefers_sidecar_over_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "iev.db"
    sidecar_root = tmp_path / "data" / "iev"
    SQLiteIEVRepository(db_path).save_snapshot(
        SESSION,
        [MoverData("BBCA", 1, 1000)],
        collected_at=datetime(2026, 6, 18, 8, 57, 0),
        collection_started_at=datetime(2026, 6, 18, 8, 56, 5),
    )
    IEVJsonSidecarWriter(sidecar_root).write_snapshot(
        SESSION,
        [MoverData("BBCA", 1, 1000)],
        captured_at=datetime(2026, 6, 18, 9, 24, 24, tzinfo=WIB),
        top_n=50,
    )
    captured = IevSessionCaptureLookup(db_path=db_path, sidecar_root=sidecar_root).captured_at_for(
        SESSION
    )
    assert captured is not None
    assert captured.astimezone(WIB).hour == 9
    assert captured.astimezone(WIB).minute == 24


def test_lookup_falls_back_to_sqlite_when_sidecar_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "iev.db"
    SQLiteIEVRepository(db_path).save_snapshot(
        SESSION,
        [MoverData("BBCA", 1, 1000)],
        collected_at=datetime(2026, 6, 18, 9, 24, 24),
        collection_started_at=datetime(2026, 6, 18, 9, 24, 0),
    )
    captured = IevSessionCaptureLookup(
        db_path=db_path, sidecar_root=tmp_path / "data" / "iev"
    ).captured_at_for(SESSION)
    assert captured is not None
    assert captured.astimezone(WIB) == datetime(2026, 6, 18, 9, 24, 24, tzinfo=WIB)


def test_lookup_returns_none_when_no_snapshot(tmp_path: Path) -> None:
    captured = IevSessionCaptureLookup(
        db_path=tmp_path / "missing.db",
        sidecar_root=tmp_path / "data" / "iev",
    ).captured_at_for(SESSION)
    assert captured is None
    assert not (tmp_path / "missing.db").exists()
