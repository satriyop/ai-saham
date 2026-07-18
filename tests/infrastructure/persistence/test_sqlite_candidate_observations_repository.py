from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)
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

    assert {row[0] for row in versions} == set(range(17))
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
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "ticker": ticker, "value": value},
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
                payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION + 1, "ticker": "BBCA"},
            )
        ]
    )

    with pytest.raises(ValueError, match="Unsupported candidate observation"):
        repo.get_latest("BBCA", day)


def test_current_schema_version_round_trips(tmp_path: Path):
    """Current-schema payloads must read back without raising."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "ticker": "BBCA"},
            )
        ]
    )

    observation = repo.get_latest("BBCA", day)
    assert observation is not None
    assert observation.payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION


def test_schema_4_observation_persists_only_sector_context(tmp_path: Path):
    """SECTOR-CONTEXT-IDENTITY: a current-schema (v4) observation whose Alpha/
    Trigger route metadata uses the canonical sector_context identity must
    save and read back unchanged."""
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
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                    "sub_signal_fingerprint": {
                        "alpha_trigger_route_metadata": [
                            {"group": "sector_context", "score": 75.0},
                        ],
                    },
                },
            )
        ]
    )

    observation = repo.get_latest("BBCA", day)
    assert observation is not None
    route_metadata = observation.payload["sub_signal_fingerprint"]["alpha_trigger_route_metadata"]
    assert route_metadata == [{"group": "sector_context", "score": 75.0}]


def test_schema_4_observation_containing_removed_market_context_fails_on_save(tmp_path: Path):
    """A schema-4 write must never persist the removed market_context Alpha/
    Trigger identity — the fail-closed boundary is enforced before any row
    is written."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    with pytest.raises(
        ValueError,
        match="schema_version=4 cannot contain removed Alpha/Trigger group 'market_context'",
    ):
        repo.save_many(
            [
                CandidateObservation(
                    ticker="BBCA",
                    snapshot_date=day,
                    captured_at=datetime(2026, 7, 3, 9, 0, 0),
                    payload={
                        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                        "ticker": "BBCA",
                        "sub_signal_fingerprint": {
                            "alpha_trigger_route_metadata": [
                                {"group": "market_context", "score": 75.0},
                            ],
                        },
                    },
                )
            ]
        )


def test_schema_4_raw_inserted_market_context_fails_on_read(tmp_path: Path):
    """A schema-4 row smuggled directly into the table (bypassing save_many's
    write guard) must still fail closed on read — the readback boundary does
    not trust stored payload contents."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

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
                CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                json.dumps(
                    {
                        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                        "ticker": "BBCA",
                        "sub_signal_fingerprint": {
                            "alpha_trigger_route_metadata": [
                                {"group": "market_context", "score": 75.0},
                            ],
                        },
                    }
                ),
                "screen_accum",
                7,
                day.isoformat(),
                "abc123",
            ),
        )
        conn.commit()

    with pytest.raises(
        ValueError,
        match="schema_version=4 cannot contain removed Alpha/Trigger group 'market_context'",
    ):
        repo.get_latest("BBCA", day)


def test_schema_4_malformed_route_metadata_fails(tmp_path: Path):
    """A schema-4 payload whose route metadata is malformed (entry without a
    non-empty string group) must fail closed rather than be silently
    discarded."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    with pytest.raises(ValueError, match="non-empty string 'group'"):
        repo.save_many(
            [
                CandidateObservation(
                    ticker="BBCA",
                    snapshot_date=day,
                    captured_at=datetime(2026, 7, 3, 9, 0, 0),
                    payload={
                        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                        "ticker": "BBCA",
                        "sub_signal_fingerprint": {
                            "alpha_trigger_route_metadata": [
                                {"score": 75.0},
                            ],
                        },
                    },
                )
            ]
        )


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


def test_legacy_schema_version_2_is_readable_but_excluded_from_canonical(tmp_path: Path):
    """HIGH-2: v2 rows (pre-HIGH-2, ambiguous coverage_score/conviction_score/
    phase_* fields) remain readable for diagnostics but are excluded from
    list_canonical_by_date now that v3 is canonical — no migration relabels
    or mutates them."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

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
                2,
                json.dumps({"schema_version": 2, "ticker": "BBCA", "coverage_score": 0.5}),
                "screen_accum",
                7,
                day.isoformat(),
                "abc123",
            ),
        )
        conn.commit()

    observation = repo.get_latest("BBCA", day)
    assert observation is not None
    assert observation.payload["schema_version"] == 2
    assert observation.payload["coverage_score"] == 0.5

    canonical = repo.list_canonical_by_date(day)
    assert len(canonical) == 0


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
                payload={
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                    "value": "second",
                },
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


def test_non_empty_config_hash_requires_current_schema_version_on_write(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    # Attempts to write a non-empty config_hash with an old schema_version must raise ValueError
    v1_obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        payload={"schema_version": 1, "ticker": "BBCA"},
        config_hash="abc123",
    )
    with pytest.raises(
        ValueError,
        match=f"requires schema_version == {CANDIDATE_OBSERVATION_SCHEMA_VERSION}",
    ):
        repo.save_many([v1_obs])


def test_list_canonical_snapshot_dates_excludes_legacy_only_dates(tmp_path: Path):
    """1. Canonical dates exclude legacy-only dates."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    canonical_day = date(2026, 7, 1)
    legacy_day = date(2026, 7, 2)

    repo.save_many([_canonical_observation(snapshot_date=canonical_day)])
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=legacy_day,
                captured_at=datetime(2026, 7, 2, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy"},
            )
        ]
    )

    assert repo.list_canonical_snapshot_dates() == [canonical_day]


def test_list_canonical_snapshot_dates_ordered_ascending(tmp_path: Path):
    """2. Canonical dates are ordered ascending."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    later = date(2026, 7, 5)
    earlier = date(2026, 7, 1)
    middle = date(2026, 7, 3)

    repo.save_many([_canonical_observation(snapshot_date=later, config_hash="hash-1")])
    repo.save_many([_canonical_observation(snapshot_date=earlier, config_hash="hash-2")])
    repo.save_many([_canonical_observation(snapshot_date=middle, config_hash="hash-3")])

    assert repo.list_canonical_snapshot_dates() == [earlier, middle, later]


def test_list_canonical_snapshot_dates_empty_result_returns_empty_list(tmp_path: Path):
    """8. Empty canonical result returns []."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)

    assert repo.list_canonical_snapshot_dates() == []


def test_list_latest_canonical_by_date_ignores_newer_legacy_row(tmp_path: Path):
    """3. Latest canonical query ignores a newer legacy row — a later-captured
    legacy row must not displace an earlier canonical row."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [_canonical_observation(captured_at=datetime(2026, 7, 3, 9, 0, 0), value="canonical")]
    )
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 10, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA", "value": "legacy-newer"},
            )
        ]
    )

    rows = repo.list_latest_canonical_by_date(day)
    assert len(rows) == 1
    assert rows[0].payload["value"] == "canonical"


def test_list_latest_canonical_by_date_returns_one_row_per_ticker(tmp_path: Path):
    """4. Latest canonical query returns one row per ticker."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            _canonical_observation(
                ticker="BBCA",
                config_hash="hash-bbca",
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                window_sessions=7,
                value="bbca_w7",
            )
        ]
    )
    repo.save_many(
        [
            _canonical_observation(
                ticker="BBCA",
                config_hash="hash-bbca-2",
                captured_at=datetime(2026, 7, 3, 9, 1, 0),
                window_sessions=30,
                value="bbca_w30",
            )
        ]
    )
    repo.save_many(
        [
            _canonical_observation(
                ticker="BBRI",
                config_hash="hash-bbri",
                captured_at=datetime(2026, 7, 3, 9, 30, 0),
                value="bbri",
            )
        ]
    )

    rows = repo.list_latest_canonical_by_date(day)
    assert [(row.ticker, row.payload["value"]) for row in rows] == [
        ("BBCA", "bbca_w30"),
        ("BBRI", "bbri"),
    ]


def test_list_latest_canonical_by_date_excludes_empty_config_hash(tmp_path: Path):
    """6. Empty config_hash is excluded."""
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
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                    "value": "no-config-hash",
                },
            )
        ]
    )

    assert repo.list_latest_canonical_by_date(day) == []
    assert repo.list_canonical_snapshot_dates() == []


def test_list_latest_canonical_by_date_excludes_schema_1_and_2(tmp_path: Path):
    """7. Schema 1/2 is excluded, even with a non-empty config_hash."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

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
                2,
                json.dumps({"schema_version": 2, "ticker": "BBCA"}),
                "screen_accum",
                7,
                day.isoformat(),
                "abc123",
            ),
        )
        conn.commit()

    assert repo.list_latest_canonical_by_date(day) == []
    assert repo.list_canonical_snapshot_dates() == []


def test_list_latest_canonical_by_date_empty_result_returns_empty_list(tmp_path: Path):
    """8. Empty canonical result returns []."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    assert repo.list_latest_canonical_by_date(day) == []


def test_list_canonical_by_date_still_returns_all_windows_alongside_latest_canonical(
    tmp_path: Path,
):
    """5. Raw canonical query (list_canonical_by_date) still returns all
    windows, distinct from the collapsed latest-per-ticker canonical query."""
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

    latest_canonical = repo.list_latest_canonical_by_date(day)
    assert len(latest_canonical) == 1

    raw_canonical = repo.list_canonical_by_date(day)
    assert len(raw_canonical) == 3
    assert {row.payload["value"] for row in raw_canonical} == {"w7", "w30", "w90"}


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


def _sample_identity() -> SignalArtifactIdentity:
    return SignalArtifactIdentity(
        artifact_id=ArtifactId(
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        semantic_compatibility_id=SemanticCompatibilityId(
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        provenance=ArtifactProvenance(
            application_revision="abc1234",
            complete_config_hash="c" * 64,
            complete_authority_registry_hash="d" * 64,
            universe_snapshot_id="univ-001",
            idx_calendar_version="2026-v3",
            session_rule_version="sr-v2",
            decision_at=datetime(2026, 7, 3, 16, 0, 0, 123456, tzinfo=timezone.utc),
            captured_at=datetime(2026, 7, 3, 9, 30, 0, 456789, tzinfo=timezone.utc),
            latest_completed_session=date(2026, 7, 3),
            analysis_as_of=date(2026, 7, 3),
            sources=(
                ArtifactSourceProvenance(
                    source_family="exchange",
                    provider="idx",
                    source_snapshot_id="snap-001",
                    observed_through=date(2026, 7, 3),
                    available_at=datetime(2026, 7, 3, 7, 0, 0, tzinfo=timezone.utc),
                    cutoff_at=datetime(2026, 7, 3, 8, 0, 0, tzinfo=timezone.utc),
                ),
            ),
        ),
    )


# ── ARTIFACT-IDENTITY Slice 3: artifact_identity persistence ──────────────────


def test_artifact_identity_defaults_to_none(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA"},
            )
        ]
    )

    obs = repo.get_latest("BBCA", day)
    assert obs is not None
    assert obs.artifact_identity is None


def test_artifact_identity_round_trips_completely(tmp_path: Path):
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    identity = _sample_identity()

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 30, 0, 456789),
                payload={
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                },
                workflow="screen_accum",
                window_sessions=7,
                data_as_of_date=day,
                config_hash="abc123",
                artifact_identity=identity,
            )
        ]
    )

    obs = repo.get_latest("BBCA", day)
    assert obs is not None
    assert obs.artifact_identity is not None
    assert obs.artifact_identity.artifact_id == identity.artifact_id
    assert obs.artifact_identity.semantic_compatibility_id == identity.semantic_compatibility_id
    assert obs.artifact_identity.provenance.application_revision == "abc1234"
    assert obs.artifact_identity.provenance.complete_config_hash == "c" * 64
    assert obs.artifact_identity.provenance.captured_at == datetime(
        2026, 7, 3, 9, 30, 0, 456789, tzinfo=timezone.utc
    )
    assert obs.artifact_identity.provenance.decision_at == datetime(
        2026, 7, 3, 16, 0, 0, 123456, tzinfo=timezone.utc
    )
    assert len(obs.artifact_identity.provenance.sources) == 1
    src = obs.artifact_identity.provenance.sources[0]
    assert src.source_family == "exchange"
    assert src.provider == "idx"
    assert src.source_snapshot_id == "snap-001"


def test_legacy_rows_without_identity_read_as_none(tmp_path: Path):
    """Rows predating the artifact-identity columns must remain readable
    with artifact_identity=None."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={"schema_version": 1, "ticker": "BBCA"},
            )
        ]
    )

    obs = repo.get_latest("BBCA", day)
    assert obs is not None
    assert obs.artifact_identity is None
    assert obs.payload["ticker"] == "BBCA"


def test_identity_preserved_across_upsert(tmp_path: Path):
    """When a canonical row is UPSERTed, the artifact_identity from the latest
    write must replace the previous identity."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)
    first_id = _sample_identity()
    second_id = SignalArtifactIdentity(
        artifact_id=ArtifactId(
            "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        ),
        semantic_compatibility_id=SemanticCompatibilityId(
            "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        ),
        provenance=ArtifactProvenance(
            application_revision="def5678",
            complete_config_hash="e" * 64,
            complete_authority_registry_hash="f" * 64,
            universe_snapshot_id="univ-002",
            idx_calendar_version="2026-v4",
            session_rule_version="sr-v3",
            decision_at=datetime(2026, 7, 4, 16, 0, 0, tzinfo=timezone.utc),
            captured_at=datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc),
            latest_completed_session=date(2026, 7, 3),
            analysis_as_of=date(2026, 7, 3),
            sources=(),
        ),
    )

    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 9, 0, 0),
                payload={
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                },
                workflow="screen_accum",
                window_sessions=7,
                data_as_of_date=day,
                config_hash="abc123",
                artifact_identity=first_id,
            )
        ]
    )
    repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 3, 10, 0, 0),
                payload={
                    "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
                    "ticker": "BBCA",
                },
                workflow="screen_accum",
                window_sessions=7,
                data_as_of_date=day,
                config_hash="abc123",
                artifact_identity=second_id,
            )
        ]
    )

    rows = repo.list_all_by_date(day)
    assert len(rows) == 1
    assert rows[0].artifact_identity is not None
    assert rows[0].artifact_identity.artifact_id == second_id.artifact_id


def test_no_artifact_id_unique_index_exists(tmp_path: Path):
    """Slice 3 must not add a unique index on artifact_id.

    Inspect PRAGMA index_list and PRAGMA index_info to catch uniquely-indexed
    artifact_id even under a non-obvious index name.
    """
    db_path = tmp_path / "data.db"
    SQLiteCandidateObservationsRepository(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        index_list = conn.execute(
            "SELECT name, \"unique\" FROM pragma_index_list('candidate_observations')"
        ).fetchall()

    for index_name, is_unique in index_list:
        if not is_unique:
            continue
        with sqlite3.connect(str(db_path)) as conn:
            columns = [
                row[2]
                for row in conn.execute(
                    "SELECT * FROM pragma_index_info(?)", (index_name,)
                )
            ]
        assert "artifact_id" not in columns, (
            f"Unique index {index_name!r} contains artifact_id — "
            "no uniqueness on artifact_id in this slice"
        )


def test_config_hash_upsert_behavior_unchanged_with_identity(tmp_path: Path):
    """Existing config_hash UPSERT (canonical replacement) must still work
    correctly when artifact_identity is present."""
    db_path = tmp_path / "data.db"
    repo = SQLiteCandidateObservationsRepository(db_path)
    day = date(2026, 7, 3)

    repo.save_many([_canonical_observation(value="first", config_hash="same-hash")])
    repo.save_many([_canonical_observation(value="second", config_hash="same-hash")])

    rows = repo.list_all_by_date(day)
    assert len(rows) == 1
    assert rows[0].payload["value"] == "second"


# ── Source contract catalog contains identity columns ─────────────────────────


def test_source_contract_catalog_includes_identity_columns():
    """The source-field contract catalog must include all three identity columns
    with null_policy='fail' (NULL is corruption),
    invalid_values=frozenset({""}) and invalid_value_policy='warn'
    (transitional empty strings warn, not fail)."""
    from src.infrastructure.persistence.source_field_contract_catalog import (
        _CANDIDATE_OBSERVATIONS_FIELDS,
        FIELD_STATS_MODE,
    )

    field_names = {c.field for c in _CANDIDATE_OBSERVATIONS_FIELDS}
    assert "artifact_id" in field_names
    assert "semantic_compatibility_id" in field_names
    assert "artifact_provenance_json" in field_names

    for c in _CANDIDATE_OBSERVATIONS_FIELDS:
        if c.field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
            assert c.null_policy == "fail", (
                f"{c.field} should have null_policy='fail' (NULL is corruption)"
            )
            assert c.invalid_values == frozenset({""}), (
                f"{c.field} should declare '' as an invalid value"
            )
            assert c.invalid_value_policy == "warn", (
                f"{c.field} should have invalid_value_policy='warn' "
                "(transitional empty values warn, not fail)"
            )

    assert FIELD_STATS_MODE[("candidate_observations", "artifact_id")] == "identity_text"
    assert (
        FIELD_STATS_MODE[("candidate_observations", "semantic_compatibility_id")]
        == "identity_text"
    )
    assert (
        FIELD_STATS_MODE[("candidate_observations", "artifact_provenance_json")] == "none"
    )
