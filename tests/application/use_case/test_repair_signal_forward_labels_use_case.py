"""Tests for RepairSignalForwardLabelsUseCase (DQ-001L)."""

from __future__ import annotations

from src.application.use_case.repair_signal_forward_labels_use_case import (
    CANDIDATE_OBSERVATIONS_TABLE_MISSING,
    DATABASE_MISSING,
    RawSignalForwardLabelsRepairState,
    RepairSignalForwardLabelsUseCase,
    SIGNAL_FORWARD_LABELS_TABLE_MISSING,
    REQUIRED_LINKAGE_COLUMNS_MISSING,
)


class _FakeReader:
    def __init__(
        self,
        state: RawSignalForwardLabelsRepairState,
        db_exists: bool = True,
    ) -> None:
        self._state = state
        self._db_exists = db_exists

    def database_exists(self) -> bool:
        return self._db_exists

    def observe_repair_state(self) -> RawSignalForwardLabelsRepairState:
        return self._state


class _FakeRepairer:
    def __init__(self, quarantined: int = 0, deleted: int = 0) -> None:
        self.ensure_called = False
        self.quarantine_calls: list[str] = []
        self._quarantined = quarantined
        self._deleted = deleted

    def ensure_quarantine_table(self) -> None:
        self.ensure_called = True

    def quarantine_and_delete_orphans(self, repair_run_id: str) -> tuple[int, int]:
        self.quarantine_calls.append(repair_run_id)
        return self._quarantined, self._deleted


def _clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def _state(**overrides) -> RawSignalForwardLabelsRepairState:
    values = dict(
        exists=True,
        source_unavailable=False,
        source_unavailable_reason=None,
        total_row_count=100,
        orphan_row_count=10,
        canonical_row_count=90,
        signal_date_min="2026-01-01",
        signal_date_max="2026-07-15",
        missing_columns=(),
    )
    values.update(overrides)
    return RawSignalForwardLabelsRepairState(**values)


# ── Dry-run ──────────────────────────────────────────────────────────────────


def test_dry_run_reports_orphan_rows_and_does_not_call_repairer():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)

    assert response.status == "FAIL"
    assert response.mode == "DRY_RUN"
    assert response.dry_run is True
    assert response.orphan_row_count == 10
    assert response.quarantined_row_count == 0
    assert response.deleted_row_count == 0
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []


def test_default_is_dry_run():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute()

    assert response.mode == "DRY_RUN"
    assert response.dry_run is True
    assert repairer.quarantine_calls == []


# ── Apply ────────────────────────────────────────────────────────────────────


def test_apply_calls_repairer_with_orphan_rows():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer(quarantined=10, deleted=10)

    response = RepairSignalForwardLabelsUseCase(
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
    repairer = _FakeRepairer(quarantined=10, deleted=10)

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "PASS"
    assert response.quarantined_row_count == 10
    assert response.deleted_row_count == 10


def test_apply_count_mismatch_returns_fail():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer(quarantined=8, deleted=8)

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.quarantined_row_count == 8


# ── Source unavailable ───────────────────────────────────────────────────────


def test_missing_database_returns_fail_no_mutation():
    reader = _FakeReader(_state(exists=False), db_exists=False)
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == DATABASE_MISSING
    assert response.mode == "APPLY"
    assert response.dry_run is False
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []


def test_missing_signal_forward_labels_table_returns_fail():
    reader = _FakeReader(_state(exists=False), db_exists=True)
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == SIGNAL_FORWARD_LABELS_TABLE_MISSING
    assert repairer.quarantine_calls == []


def test_missing_candidate_observations_table_returns_fail():
    reader = _FakeReader(
        _state(
            source_unavailable=True,
            source_unavailable_reason=CANDIDATE_OBSERVATIONS_TABLE_MISSING,
        ),
        db_exists=True,
    )
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == CANDIDATE_OBSERVATIONS_TABLE_MISSING
    assert repairer.quarantine_calls == []


def test_missing_required_linkage_columns_returns_fail():
    reader = _FakeReader(
        _state(
            source_unavailable=True,
            source_unavailable_reason=REQUIRED_LINKAGE_COLUMNS_MISSING,
            missing_columns=("snapshot_date",),
        ),
        db_exists=True,
    )
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == REQUIRED_LINKAGE_COLUMNS_MISSING
    assert "snapshot_date" in response.missing_columns
    assert repairer.quarantine_calls == []


# ── No orphan rows ────────────────────────────────────────────────────────────


def test_no_orphan_rows_returns_pass():
    reader = _FakeReader(
        _state(orphan_row_count=0, canonical_row_count=100)
    )
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=True)

    assert response.status == "PASS"
    assert response.orphan_row_count == 0
    assert repairer.quarantine_calls == []


def test_no_orphan_rows_dry_run_also_returns_pass():
    reader = _FakeReader(
        _state(orphan_row_count=0, canonical_row_count=100)
    )
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(apply=False)

    assert response.status == "PASS"
    assert response.dry_run is True


# ── Response shape ────────────────────────────────────────────────────────────


def test_response_to_dict_has_all_required_keys():
    reader = _FakeReader(_state())
    repairer = _FakeRepairer()

    response = RepairSignalForwardLabelsUseCase(
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
        "orphan_row_count",
        "canonical_row_count",
        "quarantined_row_count",
        "deleted_row_count",
        "missing_columns",
        "date_range",
        "findings",
    }
    assert required_keys.issubset(data.keys())
    assert data["artifact_type"] == "signal_forward_labels_repair"
    assert data["schema_version"] == 1
    assert data["date_range"]["signal_date_min"] == "2026-01-01"
    assert data["date_range"]["signal_date_max"] == "2026-07-15"
