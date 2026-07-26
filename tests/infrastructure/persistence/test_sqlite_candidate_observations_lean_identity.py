"""DQ-003 Slice A: lean observation-identity persistence and canonical-read.

Proves the whole-config-hash semantic_compatibility_id + observation_contract
round-trip, that the compatibility id is a cohort tag (NOT part of the upsert
key), and that a contract-less row is excluded from canonical reads.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)

_DAY = date(2026, 7, 3)
_ID_1 = SemanticCompatibilityId("sha256:" + "1" * 64)
_ID_2 = SemanticCompatibilityId("sha256:" + "2" * 64)


def _lean_observation(
    *,
    semantic_compatibility_id: SemanticCompatibilityId | None = _ID_1,
    observation_contract: str | None = ACCUMULATION_DISCOVERY_CONTRACT,
    captured_at: datetime = datetime(2026, 7, 3, 9, 0, 0),
    value: str = "v1",
) -> CandidateObservation:
    return CandidateObservation(
        ticker="BBCA",
        snapshot_date=_DAY,
        captured_at=captured_at,
        payload={
            "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            "ticker": "BBCA",
            "value": value,
        },
        workflow="screen_accum",
        window_sessions=7,
        data_as_of_date=_DAY,
        config_hash="cfg-hash",
        decision_at=datetime(2026, 7, 3, 8, 0, 0),
        latest_completed_session=_DAY,
        analysis_as_of=_DAY,
        observation_contract=observation_contract,
        semantic_compatibility_id=semantic_compatibility_id,
    )


def test_lean_identity_round_trips(tmp_path: Path):
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    repo.save_many([_lean_observation()])

    read = repo.get_latest("BBCA", _DAY)
    assert read is not None
    assert read.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert read.semantic_compatibility_id == _ID_1
    # Lean rows leave the parked full artifact identity absent — the read path
    # must NOT route the lone semantic_compatibility_id through the
    # all-three-or-none codec.
    assert read.artifact_identity is None


def test_same_config_two_writes_stay_one_row_with_stable_id(tmp_path: Path):
    """Two runs with the same config (same id, same canonical key) upsert to a
    single row — no duplicate, id unchanged."""
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    repo.save_many([_lean_observation(value="first")])
    repo.save_many(
        [_lean_observation(value="second", captured_at=datetime(2026, 7, 3, 10, 0, 0))]
    )

    rows = repo.list_all_by_date(_DAY)
    assert len(rows) == 1
    assert rows[0].payload["value"] == "second"
    assert rows[0].semantic_compatibility_id == _ID_1


def test_differing_compat_id_alone_does_not_duplicate(tmp_path: Path):
    """The semantic_compatibility_id is a cohort tag, NOT part of the upsert
    key: a second write differing ONLY in the id replaces the row in place."""
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    repo.save_many([_lean_observation(semantic_compatibility_id=_ID_1, value="first")])
    repo.save_many(
        [
            _lean_observation(
                semantic_compatibility_id=_ID_2,
                value="second",
                captured_at=datetime(2026, 7, 3, 11, 0, 0),
            )
        ]
    )

    rows = repo.list_all_by_date(_DAY)
    assert len(rows) == 1  # not duplicated by the differing id
    assert rows[0].semantic_compatibility_id == _ID_2  # replaced in place
    assert rows[0].payload["value"] == "second"


def test_row_without_contract_is_excluded_from_canonical_reads(tmp_path: Path):
    """A row with full provenance + config_hash but NO observation_contract is
    not a canonical accumulation-discovery observation."""
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    repo.save_many(
        [
            _lean_observation(
                observation_contract=None,
                semantic_compatibility_id=_ID_1,
            )
        ]
    )

    # Present in raw storage...
    assert len(repo.list_all_by_date(_DAY)) == 1
    # ...but excluded from every canonical read.
    assert repo.list_canonical_by_date(_DAY) == []
    assert repo.list_latest_canonical_by_date(_DAY) == []
    assert repo.list_canonical_snapshot_dates() == []


def test_contract_row_is_included_in_canonical_reads(tmp_path: Path):
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    repo.save_many([_lean_observation()])

    assert len(repo.list_canonical_by_date(_DAY)) == 1
    assert len(repo.list_latest_canonical_by_date(_DAY)) == 1
    assert repo.list_canonical_snapshot_dates() == [_DAY]


def test_removed_unversioned_contract_is_rejected_on_write(tmp_path: Path):
    repo = SQLiteCandidateObservationsRepository(tmp_path / "data.db")
    with pytest.raises(ValueError, match="observation_contract"):
        repo.save_many(
            [_lean_observation(observation_contract="accumulation-discovery")]
        )
