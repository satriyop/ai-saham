from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)


def test_save_and_get_latest_observation(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many([
        CandidateObservation(
            ticker="bbca",
            snapshot_date=day,
            captured_at=datetime(2026, 7, 3, 9, 0, 0),
            payload={
                "schema_version": 1,
                "artifact_type": "candidate_observation",
                "ticker": "BBCA",
                "snapshot_date": day.isoformat(),
                "signal": {"assessment": {"score": 70}},
            },
        ),
        CandidateObservation(
            ticker="BBCA",
            snapshot_date=day,
            captured_at=datetime(2026, 7, 3, 10, 0, 0),
            payload={
                "schema_version": 1,
                "artifact_type": "candidate_observation",
                "ticker": "BBCA",
                "snapshot_date": day.isoformat(),
                "signal": {"assessment": {"score": 80}},
            },
        ),
    ])

    obs = repo.get_latest("bbca", day)

    assert obs is not None
    assert obs.ticker == "BBCA"
    assert obs.payload["signal"]["assessment"]["score"] == 80


def test_schema_created_via_migration_runner(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteCandidateObservationsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace=?",
            ("candidate_observations",),
        ).fetchall()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

    assert {row[0] for row in versions} == {0, 1}
    assert "candidate_observations" in {row[0] for row in tables}


def test_unsupported_schema_version_rejected(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many([
        CandidateObservation(
            ticker="BBCA",
            snapshot_date=day,
            captured_at=datetime(2026, 7, 3, 9, 0, 0),
            payload={"schema_version": 2, "ticker": "BBCA"},
        )
    ])

    with pytest.raises(ValueError, match="Unsupported candidate observation"):
        repo.get_latest("BBCA", day)
