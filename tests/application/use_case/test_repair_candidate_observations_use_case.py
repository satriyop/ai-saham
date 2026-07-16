"""Tests for RepairCandidateObservationsUseCase (DQ-001J)."""

from __future__ import annotations

from src.application.use_case.repair_candidate_observations_use_case import (
    CANDIDATE_OBSERVATIONS_TABLE_MISSING,
    DATABASE_MISSING,
    RawCandidateObservationsRepairState,
    RepairCandidateObservationsUseCase,
)


class _FakeReader:
    def __init__(
        self,
        state: RawCandidateObservationsRepairState,
        db_exists: bool = True,
    ) -> None:
        self._state = state
        self._db_exists = db_exists

    def database_exists(self) -> bool:
        return self._db_exists

    def observe_repair_state(self) -> RawCandidateObservationsRepairState:
        return self._state


class _FakeRepairer:
    def __init__(self, quarantined: int = 0, deleted: int = 0) -> None:
        self.ensure_called = False
        self.quarantine_calls: list[str] = []
        self._quarantined = quarantined
        self._deleted = deleted

    def ensure_quarantine_table(self) -> None:
        self.ensure_called = True

    def quarantine_and_delete_legacy(self, repair_run_id: str) -> tuple[int, int]:
        self.quarantine_calls.append(repair_run_id)
        return self._quarantined, self._deleted


def _clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def _state(**overrides) -> RawCandidateObservationsRepairState:
    values = dict(
        exists=True,
        total_row_count=10,
        legacy_row_count=4,
        canonical_row_count=6,
        snapshot_date_min="2026-01-01",
        snapshot_date_max="2026-07-15",
        latest_snapshot_date="2026-07-15",
        latest_legacy_row_count=1,
        latest_canonical_row_count=2,
        missing_columns=(),
    )
    values.update(overrides)
    return RawCandidateObservationsRepairState(**values)


# ── Dry-run ──────────────────────────────────────────────────────────────────


def test_dry_run_reports_legacy_rows_and_does_not_call_repairer():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)

    assert response.status == "FAIL"
    assert response.mode == "DRY_RUN"
    assert response.dry_run is True
    assert response.legacy_row_count == 4
    assert response.quarantined_row_count == 0
    assert response.deleted_row_count == 0
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []


def test_default_is_dry_run():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute()

    assert response.mode == "DRY_RUN"
    assert response.dry_run is True
    assert repairer.quarantine_calls == []


# ── Apply ────────────────────────────────────────────────────────────────────


def test_apply_calls_repairer_with_legacy_rows():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer(quarantined=4, deleted=4)

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.mode == "APPLY"
    assert response.dry_run is False
    assert repairer.ensure_called is True
    assert len(repairer.quarantine_calls) == 1
    assert isinstance(repairer.quarantine_calls[0], str)
    assert response.repair_run_id == repairer.quarantine_calls[0]


def test_apply_success_returns_pass():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer(quarantined=4, deleted=4)

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "PASS"
    assert response.quarantined_row_count == 4
    assert response.deleted_row_count == 4


def test_apply_count_mismatch_returns_fail():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer(quarantined=3, deleted=3)

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.quarantined_row_count == 3


# ── Source unavailable ───────────────────────────────────────────────────────


def test_missing_database_returns_fail_no_mutation():
    reader = _FakeReader(_state(exists=False), db_exists=False)
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == DATABASE_MISSING
    assert response.mode == "APPLY"
    assert response.dry_run is False
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []


def test_missing_table_returns_fail_no_mutation():
    reader = _FakeReader(_state(exists=False), db_exists=True)
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == CANDIDATE_OBSERVATIONS_TABLE_MISSING
    assert repairer.quarantine_calls == []


# ── No legacy rows ───────────────────────────────────────────────────────────


def test_no_legacy_rows_returns_pass():
    reader = _FakeReader(_state(legacy_row_count=0, canonical_row_count=10))
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "PASS"
    assert response.legacy_row_count == 0
    assert repairer.quarantine_calls == []


def test_no_legacy_rows_dry_run_also_returns_pass():
    reader = _FakeReader(_state(legacy_row_count=0, canonical_row_count=10))
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)

    assert response.status == "PASS"
    assert response.dry_run is True


# ── Missing config_hash column ───────────────────────────────────────────────


def test_missing_config_hash_column_means_all_rows_legacy():
    reader = _FakeReader(
        _state(
            legacy_row_count=10,
            canonical_row_count=0,
            missing_columns=("config_hash",),
        )
    )
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)

    assert response.legacy_row_count == 10
    assert response.canonical_row_count == 0
    assert "config_hash" in response.missing_columns
    codes = {f["code"] for f in response.findings}
    assert "IDENTITY_COLUMN_MISSING" in codes


# ── Response shape ───────────────────────────────────────────────────────────


def test_response_to_dict_has_all_required_keys():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairCandidateObservationsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)
    data = response.to_dict()

    required_keys = {
        "artifact_type",
        "schema_version",
        "generated_at",
        "mode",
        "status",
        "source_available",
        "source_unavailable_reason",
        "dry_run",
        "repair_run_id",
        "total_row_count",
        "legacy_row_count",
        "canonical_row_count",
        "quarantined_row_count",
        "deleted_row_count",
        "missing_columns",
        "date_range",
        "latest_snapshot",
        "findings",
    }
    assert required_keys.issubset(data.keys())
    assert data["artifact_type"] == "candidate_observations_repair"
    assert data["schema_version"] == 1
    assert data["date_range"]["snapshot_date_min"] == "2026-01-01"
    assert data["date_range"]["snapshot_date_max"] == "2026-07-15"
    assert data["latest_snapshot"]["snapshot_date"] == "2026-07-15"
