from __future__ import annotations

import json
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

    assert {row[0] for row in versions} == set(range(14))
    assert "candidate_observations" in {row[0] for row in tables}


def _canonical_observation(
    *,
    ticker: str = "BBCA",
    snapshot_date: date = date(2026, 7, 3),
    captured_at: datetime = datetime(2026, 7, 3, 9, 0, 0),
    window_sessions: int = 7,
    data_as_of_date: date = date(2026, 7, 3),
    config_hash: str = "abc123",
    value: str = "v1",
) -> CandidateObservation:
    return CandidateObservation(
        ticker=ticker,
        snapshot_date=snapshot_date,
        captured_at=captured_at,
        payload={"schema_version": 2, "ticker": ticker, "value": value},
        workflow="screen_accum",
        window_sessions=window_sessions,
        data_as_of_date=data_as_of_date,
        config_hash=config_hash,
    )


def test_duplicate_canonical_identity_replaces_row_not_appends(tmp_path: Path):
    """Same (ticker, snapshot_date, workflow, window_sessions, data_as_of_date,
    config_hash) saved twice must UPSERT — row count stays 1, payload replaced."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many([_canonical_observation(value="first")])
    repo.save_many(
        [
            _canonical_observation(
                value="second", captured_at=datetime(2026, 7, 3, 10, 0, 0)
            )
        ]
    )

    rows = repo.list_all_by_date(day)
    assert len(rows) == 1
    assert rows[0].payload["value"] == "second"
    assert rows[0].captured_at == datetime(2026, 7, 3, 10, 0, 0)


def test_different_window_sessions_creates_separate_canonical_row(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many([_canonical_observation(window_sessions=7, value="w7")])
    repo.save_many([_canonical_observation(window_sessions=30, value="w30")])

    rows = repo.list_all_by_date(day)
    assert len(rows) == 2
    assert {row.payload["value"] for row in rows} == {"w7", "w30"}


def test_different_data_as_of_date_creates_separate_canonical_row(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [_canonical_observation(data_as_of_date=date(2026, 7, 3), value="fresh")]
    )
    repo.save_many(
        [_canonical_observation(data_as_of_date=date(2026, 7, 2), value="stale")]
    )

    rows = repo.list_all_by_date(day)
    assert len(rows) == 2
    assert {row.payload["value"] for row in rows} == {"fresh", "stale"}


def test_different_config_hash_creates_separate_canonical_row(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many([_canonical_observation(config_hash="hash-a", value="a")])
    repo.save_many([_canonical_observation(config_hash="hash-b", value="b")])

    rows = repo.list_all_by_date(day)
    assert len(rows) == 2
    assert {row.payload["value"] for row in rows} == {"a", "b"}


def test_legacy_rows_without_config_hash_remain_readable_and_unaffected(
    tmp_path: Path,
):
    """Pre-migration rows (config_hash='') are excluded from the canonical
    uniqueness constraint and keep appending, matching pre-S1 behavior — old
    observations must still be readable."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    legacy = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy"},
    )
    repo.save_many([legacy])
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 30, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy-2"},
            )
        ]
    )

    rows = repo.list_all_by_date(day)
    assert len(rows) == 2
    assert {row.payload["value"] for row in rows} == {"legacy", "legacy-2"}


def test_list_canonical_by_date_returns_every_window_not_just_latest(tmp_path: Path):
    """S1 regression: list_by_date() collapses to latest-per-ticker (a
    display convenience) and must NOT be used for label generation.
    list_canonical_by_date() must return all canonical rows for a ticker —
    one per window_sessions — so every recorded window can be labeled."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            _canonical_observation(
                window_sessions=7,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                value="w7",
            ),
            _canonical_observation(
                window_sessions=30,
                captured_at=datetime(2026, 7, 3, 9, 1, 0),
                value="w30",
            ),
            _canonical_observation(
                window_sessions=90,
                captured_at=datetime(2026, 7, 3, 9, 2, 0),
                value="w90",
            ),
        ]
    )

    latest_only = repo.list_by_date(day)
    assert len(latest_only) == 1
    assert latest_only[0].payload["value"] == "w90"

    canonical = repo.list_canonical_by_date(day)
    assert len(canonical) == 3
    assert {row.payload["value"] for row in canonical} == {"w7", "w30", "w90"}
    assert {row.window_sessions for row in canonical} == {7, 30, 90}


def test_list_canonical_by_date_excludes_legacy_rows(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    legacy = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy"},
    )
    repo.save_many([legacy])
    repo.save_many([_canonical_observation(value="canonical")])

    canonical = repo.list_canonical_by_date(day)
    assert len(canonical) == 1
    assert canonical[0].payload["value"] == "canonical"


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
                payload={"schema_version": 3, "ticker": "BBCA"},
            )
        ]
    )

    with pytest.raises(ValueError, match="Unsupported candidate observation"):
        repo.get_latest("BBCA", day)


def test_current_schema_version_2_round_trips(tmp_path: Path):
    """Task HIGH-1 bumped the canonical schema to v2 (typed benchmark
    excess-return fields replace the old rs_vs_ihsg_*_at_signal keys) — v2
    payloads must read back without raising."""
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

    observation = repo.get_latest("BBCA", day)
    assert observation is not None
    assert observation.payload["schema_version"] == 2


def test_legacy_schema_version_1_is_readable_but_not_canonical(tmp_path: Path):
    """v1 rows (pre-HIGH-1) must remain readable for history/audit purposes,
    but their payload never contains the corrected typed benchmark
    excess-return keys — no migration fabricates them."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={
                    "schema_version": 1,
                    "ticker": "BBCA",
                    "sub_signal_fingerprint": {
                        "rs_vs_ihsg_5d_at_signal": -1.2,
                        "rs_vs_ihsg_20d_at_signal": -3.4,
                    },
                },
            )
        ]
    )

    observation = repo.get_latest("BBCA", day)
    assert observation is not None
    assert observation.payload["schema_version"] == 1
    fingerprint = observation.payload["sub_signal_fingerprint"]
    assert "benchmark_excess_return_5_session" not in fingerprint
    assert "benchmark_excess_return_20_session" not in fingerprint


def test_effective_session_provenance_round_trips(tmp_path: Path):
    """DQ-002E: saving an observation with provenance must round-trip every
    new field exactly, including a resolver with no notes vs. one with notes."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "v1"},
                decision_at=datetime(2026, 7, 3, 16, 0, 0),
                latest_completed_session=date(2026, 7, 3),
                analysis_as_of=date(2026, 7, 3),
                market_session_name="AFTER_CLOSE",
                is_eod_pending=False,
                resolution_source="ihsg_cache_same_day",
                resolution_notes=("note one", "note two"),
            )
        ]
    )

    obs = repo.get_latest("BBCA", day)

    assert obs is not None
    assert obs.decision_at == datetime(2026, 7, 3, 16, 0, 0)
    assert obs.latest_completed_session == date(2026, 7, 3)
    assert obs.analysis_as_of == date(2026, 7, 3)
    assert obs.market_session_name == "AFTER_CLOSE"
    assert obs.is_eod_pending is False
    assert obs.resolution_source == "ihsg_cache_same_day"
    assert obs.resolution_notes == ("note one", "note two")


def test_legacy_rows_with_no_provenance_read_as_none(tmp_path: Path):
    """Rows saved before DQ-002E (or with no effective_session available)
    must remain readable with every new field defaulting to None/empty."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy"},
            )
        ]
    )

    obs = repo.get_latest("BBCA", day)

    assert obs is not None
    assert obs.decision_at is None
    assert obs.latest_completed_session is None
    assert obs.analysis_as_of is None
    assert obs.market_session_name is None
    assert obs.is_eod_pending is None
    assert obs.resolution_source is None
    assert obs.resolution_notes == ()


def test_provenance_only_change_does_not_create_new_canonical_row(tmp_path: Path):
    """Identity is (ticker, snapshot_date, workflow, window_sessions,
    data_as_of_date, config_hash) — provenance fields must never affect it."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            _canonical_observation(value="first"),
        ]
    )
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 10, 0, 0),
                payload={"schema_version": 2, "ticker": "BBCA", "value": "second"},
                workflow="screen_accum",
                window_sessions=7,
                data_as_of_date=day,
                config_hash="abc123",
                decision_at=datetime(2026, 7, 3, 16, 0, 0),
                latest_completed_session=day,
                analysis_as_of=day,
                market_session_name="AFTER_CLOSE",
                is_eod_pending=False,
                resolution_source="ihsg_cache_same_day",
                resolution_notes=("note",),
            )
        ]
    )

    rows = repo.list_all_by_date(day)
    assert len(rows) == 1
    assert rows[0].payload["value"] == "second"
    assert rows[0].resolution_source == "ihsg_cache_same_day"


def test_non_empty_config_hash_requires_schema_version_2_on_write(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    # Attempts to write a non-empty config_hash with schema_version 1 must raise ValueError
    v1_obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        payload={"schema_version": 1, "ticker": "BBCA"},
        config_hash="abc123",
    )
    with pytest.raises(ValueError, match="requires schema_version == 2"):
        repo.save_many([v1_obs])


def test_list_canonical_by_date_excludes_v1_payloads_with_non_empty_config_hash(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    # Bypass the validation of save_many to insert a row with schema_version = 1 and non-empty config_hash
    with repo._connect() as conn:
        conn.execute(
            """
            INSERT INTO candidate_observations (
                ticker, snapshot_date, captured_at, schema_version, payload_json,
                workflow, window_sessions, data_as_of_date, config_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "BBCA",
                day.isoformat(),
                datetime(2026, 7, 3, 9, 0, 0).isoformat(),
                1,
                json.dumps({"schema_version": 1, "ticker": "BBCA"}),
                "screen_accum",
                7,
                day.isoformat(),
                "abc123",
            ),
        )
        conn.commit()

    # Now verify that it is readable but excluded from canonical results
    obs = repo.get_latest("BBCA", day)
    assert obs is not None
    assert obs.payload["schema_version"] == 1
    assert obs.config_hash == "abc123"

    canonical = repo.list_canonical_by_date(day)
    assert len(canonical) == 0
