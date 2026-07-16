"""
DQ-001J — deterministic candidate_observations quarantine repair command.

Moves legacy candidate_observations rows (config_hash IS NULL or empty after
trim) out of the canonical table into a quarantine table, without losing
them. Default mode is dry-run (report only, no mutation). --apply performs
the quarantine+delete inside a single transaction.

Legacy definition: config_hash is NULL or empty after trim.
If the config_hash column itself is missing, every row is legacy.

Layer: Application
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

DATABASE_MISSING = "DATABASE_MISSING"
CANDIDATE_OBSERVATIONS_TABLE_MISSING = "CANDIDATE_OBSERVATIONS_TABLE_MISSING"

_SOURCE_UNAVAILABLE_REASONS = (DATABASE_MISSING, CANDIDATE_OBSERVATIONS_TABLE_MISSING)


@dataclass(frozen=True)
class RawCandidateObservationsRepairState:
    """Raw aggregate facts about candidate_observations, uninterpreted.

    The reader never classifies or evaluates — it only collects SQL
    aggregates and returns them uninterpreted.
    """

    exists: bool
    total_row_count: int = 0
    legacy_row_count: int = 0
    canonical_row_count: int = 0
    snapshot_date_min: str | None = None
    snapshot_date_max: str | None = None
    latest_snapshot_date: str | None = None
    latest_legacy_row_count: int = 0
    latest_canonical_row_count: int = 0
    missing_columns: tuple[str, ...] = ()


class CandidateObservationsRepairReader(Protocol):
    """Read-only observer of candidate_observations. Must never mutate the database."""

    def database_exists(self) -> bool: ...

    def observe_repair_state(self) -> RawCandidateObservationsRepairState: ...


class CandidateObservationsRepairer(Protocol):
    """Mutating port for the candidate_observations quarantine/delete workflow."""

    def ensure_quarantine_table(self) -> None: ...

    def quarantine_and_delete_legacy(self, repair_run_id: str) -> tuple[int, int]:
        """Quarantine+delete legacy rows in one transaction.

        Returns (quarantined_row_count, deleted_row_count). Raises and rolls
        back if the deleted count does not match the quarantined count.
        """
        ...


@dataclass(frozen=True)
class RepairCandidateObservationsResponse:
    artifact_type: str = "candidate_observations_repair"
    schema_version: int = 1
    generated_at: str = ""
    mode: str = "DRY_RUN"  # "DRY_RUN" | "APPLY"
    status: str = "FAIL"
    source_available: bool = True
    source_unavailable_reason: str | None = None
    dry_run: bool = True
    repair_run_id: str = ""

    total_row_count: int = 0
    legacy_row_count: int = 0
    canonical_row_count: int = 0
    quarantined_row_count: int = 0
    deleted_row_count: int = 0

    missing_columns: tuple[str, ...] = ()

    snapshot_date_min: str | None = None
    snapshot_date_max: str | None = None

    latest_snapshot_date: str | None = None
    latest_snapshot_legacy_rows: int = 0
    latest_snapshot_canonical_rows: int = 0

    findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "mode": self.mode,
            "status": self.status,
            "source_available": self.source_available,
            "source_unavailable_reason": self.source_unavailable_reason,
            "dry_run": self.dry_run,
            "repair_run_id": self.repair_run_id,
            "total_row_count": self.total_row_count,
            "legacy_row_count": self.legacy_row_count,
            "canonical_row_count": self.canonical_row_count,
            "quarantined_row_count": self.quarantined_row_count,
            "deleted_row_count": self.deleted_row_count,
            "missing_columns": list(self.missing_columns),
            "date_range": {
                "snapshot_date_min": self.snapshot_date_min,
                "snapshot_date_max": self.snapshot_date_max,
            },
            "latest_snapshot": {
                "snapshot_date": self.latest_snapshot_date,
                "legacy_rows": self.latest_snapshot_legacy_rows,
                "canonical_rows": self.latest_snapshot_canonical_rows,
            },
            "findings": [dict(f) for f in self.findings],
        }


def _default_clock() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepairCandidateObservationsUseCase:
    """Repair (quarantine + delete) legacy candidate_observations rows."""

    _ARTIFACT_TYPE = "candidate_observations_repair"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: CandidateObservationsRepairReader,
        repairer: CandidateObservationsRepairer,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._repairer = repairer
        self._clock = clock or _default_clock

    def execute(self, apply: bool = False) -> RepairCandidateObservationsResponse:
        generated_at = self._clock()
        repair_run_id = str(uuid.uuid4())
        mode = "APPLY" if apply else "DRY_RUN"
        dry_run = not apply

        source_unavailable_reason: str | None = None
        if not self._reader.database_exists():
            source_unavailable_reason = DATABASE_MISSING
        else:
            state = self._reader.observe_repair_state()
            if not state.exists:
                source_unavailable_reason = CANDIDATE_OBSERVATIONS_TABLE_MISSING

        if source_unavailable_reason is not None:
            return RepairCandidateObservationsResponse(
                generated_at=generated_at,
                mode=mode,
                status="FAIL",
                source_available=False,
                source_unavailable_reason=source_unavailable_reason,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                findings=[
                    {
                        "severity": "FAIL",
                        "code": "SOURCE_UNAVAILABLE",
                        "message": (
                            f"candidate_observations is not accessible: "
                            f"{source_unavailable_reason}"
                        ),
                    }
                ],
            )

        findings: list[dict] = []
        for col in state.missing_columns:
            findings.append(
                {
                    "severity": "WARN",
                    "code": "IDENTITY_COLUMN_MISSING",
                    "message": (
                        f"Column '{col}' does not exist in candidate_observations. "
                        f"All {state.total_row_count} row(s) are treated as legacy "
                        "for this field."
                    ),
                }
            )

        total = state.total_row_count
        legacy = state.legacy_row_count
        canonical = state.canonical_row_count

        if legacy == 0:
            findings.append(
                {
                    "severity": "INFO",
                    "code": "NO_LEGACY_ROWS",
                    "message": "No legacy candidate_observations rows found.",
                }
            )
            return RepairCandidateObservationsResponse(
                generated_at=generated_at,
                mode=mode,
                status="PASS",
                source_available=True,
                source_unavailable_reason=None,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                total_row_count=total,
                legacy_row_count=0,
                canonical_row_count=canonical,
                quarantined_row_count=0,
                deleted_row_count=0,
                missing_columns=state.missing_columns,
                snapshot_date_min=state.snapshot_date_min,
                snapshot_date_max=state.snapshot_date_max,
                latest_snapshot_date=state.latest_snapshot_date,
                latest_snapshot_legacy_rows=state.latest_legacy_row_count,
                latest_snapshot_canonical_rows=state.latest_canonical_row_count,
                findings=findings,
            )

        if dry_run:
            findings.append(
                {
                    "severity": "FAIL",
                    "code": "LEGACY_ROWS_PRESENT",
                    "message": (
                        f"{legacy} of {total} row(s) are legacy and remain "
                        "unresolved. Run with --apply to quarantine them."
                    ),
                }
            )
            return RepairCandidateObservationsResponse(
                generated_at=generated_at,
                mode=mode,
                status="FAIL",
                source_available=True,
                source_unavailable_reason=None,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                total_row_count=total,
                legacy_row_count=legacy,
                canonical_row_count=canonical,
                quarantined_row_count=0,
                deleted_row_count=0,
                missing_columns=state.missing_columns,
                snapshot_date_min=state.snapshot_date_min,
                snapshot_date_max=state.snapshot_date_max,
                latest_snapshot_date=state.latest_snapshot_date,
                latest_snapshot_legacy_rows=state.latest_legacy_row_count,
                latest_snapshot_canonical_rows=state.latest_canonical_row_count,
                findings=findings,
            )

        self._repairer.ensure_quarantine_table()
        quarantined, deleted = self._repairer.quarantine_and_delete_legacy(repair_run_id)

        is_success = quarantined == deleted == legacy
        status = "PASS" if is_success else "FAIL"
        findings.append(
            {
                "severity": "INFO" if is_success else "FAIL",
                "code": "LEGACY_ROWS_QUARANTINED" if is_success else "QUARANTINE_COUNT_MISMATCH",
                "message": (
                    f"Quarantined and deleted {quarantined} of {legacy} legacy row(s)."
                    if is_success
                    else (
                        f"Expected to quarantine {legacy} legacy row(s), "
                        f"quarantined {quarantined} and deleted {deleted}."
                    )
                ),
            }
        )

        return RepairCandidateObservationsResponse(
            generated_at=generated_at,
            mode=mode,
            status=status,
            source_available=True,
            source_unavailable_reason=None,
            dry_run=dry_run,
            repair_run_id=repair_run_id,
            total_row_count=total,
            legacy_row_count=legacy,
            canonical_row_count=canonical,
            quarantined_row_count=quarantined,
            deleted_row_count=deleted,
            missing_columns=state.missing_columns,
            snapshot_date_min=state.snapshot_date_min,
            snapshot_date_max=state.snapshot_date_max,
            latest_snapshot_date=state.latest_snapshot_date,
            latest_snapshot_legacy_rows=state.latest_legacy_row_count,
            latest_snapshot_canonical_rows=state.latest_canonical_row_count,
            findings=findings,
        )
