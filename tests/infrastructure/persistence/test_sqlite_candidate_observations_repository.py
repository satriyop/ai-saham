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

    repo.save_many(
        [
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
        ]
    )

    obs = repo.get_latest("bbca", day)

    assert obs is not None
    assert obs.ticker == "BBCA"
    assert obs.payload["signal"]["assessment"]["score"] == 80


def test_get_at_returns_specific_observation_by_captured_at(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    older = datetime(2026, 7, 3, 9, 0, 0)
    newer = datetime(2026, 7, 3, 10, 0, 0)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=older,
                payload={"schema_version": 1, "ticker": "BBCA", "value": "older"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=newer,
                payload={"schema_version": 1, "ticker": "BBCA", "value": "newer"},
            ),
        ]
    )

    obs = repo.get_at("bbca", day, older)

    assert obs is not None
    assert obs.captured_at == older
    assert obs.payload["value"] == "older"


def test_list_recent_returns_prior_observations_newest_first(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=date(2026, 7, 1),
                captured_at=datetime(2026, 7, 1, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "old"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=date(2026, 7, 2),
                captured_at=datetime(2026, 7, 2, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "mid"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=date(2026, 7, 3),
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "same_day"},
            ),
        ]
    )

    rows = repo.list_recent("bbca", before_date=date(2026, 7, 3), limit=5)

    assert [row.payload["value"] for row in rows] == ["mid", "old"]


def test_list_by_date_returns_latest_observation_per_ticker(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "bbca_old"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 10, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "bbca_new"},
            ),
            CandidateObservation(
                ticker="BBRI",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 30, 0),
                payload={"schema_version": 1, "ticker": "BBRI", "value": "bbri"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=date(2026, 7, 2),
                captured_at=datetime(2026, 7, 2, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "prior"},
            ),
        ]
    )

    rows = repo.list_by_date(day)

    assert [(row.ticker, row.payload["value"]) for row in rows] == [
        ("BBCA", "bbca_new"),
        ("BBRI", "bbri"),
    ]


def test_list_all_by_date_returns_raw_observation_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "bbca_old"},
            ),
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 10, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "bbca_new"},
            ),
            CandidateObservation(
                ticker="BBRI",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 30, 0),
                payload={"schema_version": 1, "ticker": "BBRI", "value": "bbri"},
            ),
        ]
    )

    rows = repo.list_all_by_date(day)

    assert [row.payload["value"] for row in rows] == [
        "bbca_new",
        "bbca_old",
        "bbri",
    ]


def test_schema_created_via_migration_runner(tmp_path: Path):
    db_path = tmp_path / "data.db"
    SQLiteCandidateObservationsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        versions = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace=?",
            ("candidate_observations",),
        ).fetchall()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    assert {row[0] for row in versions} == {0, 1}
    assert "candidate_observations" in {row[0] for row in tables}


def test_unsupported_schema_version_rejected(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 2, "ticker": "BBCA"},
            )
        ]
    )

    with pytest.raises(ValueError, match="Unsupported candidate observation"):
        repo.get_latest("BBCA", day)
