"""
DQ-001L — deterministic signal_forward_labels quarantine repair command.

Moves orphan signal_forward_labels rows (rows whose (ticker, signal_date,
observation_captured_at) have no matching candidate_observations row) out of
the canonical table into a quarantine table, without losing them.  Default
mode is dry-run (report only, no mutation).  --apply performs the
quarantine+delete inside a single transaction.

If candidate_observations is missing or lacks required join columns, the
command reports source-unavailable FAIL and performs no mutation — a missing
candidate_observations side is not proof of orphanhood.

Layer: Application
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

DATABASE_MISSING = "DATABASE_MISSING"
SIGNAL_FORWARD_LABELS_TABLE_MISSING = "SIGNAL_FORWARD_LABELS_TABLE_MISSING"
CANDIDATE_OBSERVATIONS_TABLE_MISSING = "CANDIDATE_OBSERVATIONS_TABLE_MISSING"
REQUIRED_LINKAGE_COLUMNS_MISSING = "REQUIRED_LINKAGE_COLUMNS_MISSING"

_SOURCE_UNAVAILABLE_REASONS = (
    DATABASE_MISSING,
    SIGNAL_FORWARD_LABELS_TABLE_MISSING,
    CANDIDATE_OBSERVATIONS_TABLE_MISSING,
    REQUIRED_LINKAGE_COLUMNS_MISSING,
)


@dataclass(frozen=True)
class RawSignalForwardLabelsRepairState:
    """Raw aggregate facts about signal_forward_labels, uninterpreted.

    The reader never classifies or evaluates — it only collects SQL
    aggregates and returns them uninterpreted.
    """

    exists: bool
    source_unavailable: bool = False
    source_unavailable_reason: str | None = None
    total_row_count: int = 0
    orphan_row_count: int = 0
    canonical_row_count: int = 0
    signal_date_min: str | None = None
    signal_date_max: str | None = None
    missing_columns: tuple[str, ...] = ()


class SignalForwardLabelsRepairReader(Protocol):
    """Read-only observer of signal_forward_labels.  Must never mutate."""

    def database_exists(self) -> bool: ...

    def observe_repair_state(self) -> RawSignalForwardLabelsRepairState: ...


class SignalForwardLabelsRepairer(Protocol):
    """Mutating port for the signal_forward_labels quarantine/delete workflow."""

    def ensure_quarantine_table(self) -> None: ...

    def quarantine_and_delete_orphans(self, repair_run_id: str) -> tuple[int, int]:
        """Quarantine+delete orphan rows in one transaction.

        Returns (quarantined_row_count, deleted_row_count).  Raises and
        rolls back if the deleted count does not match the quarantined
        count.
        """
        ...


@dataclass(frozen=True)
class RepairSignalForwardLabelsResponse:
    artifact_type: str = "signal_forward_labels_repair"
    schema_version: int = 1
    generated_at: str = ""
    mode: str = "DRY_RUN"
    status: str = "FAIL"
    source_available: bool = True
    source_unavailable_reason: str | None = None
    dry_run: bool = True
    repair_run_id: str = ""

    total_row_count: int = 0
    orphan_row_count: int = 0
    canonical_row_count: int = 0
    quarantined_row_count: int = 0
    deleted_row_count: int = 0

    missing_columns: tuple[str, ...] = ()

    signal_date_min: str | None = None
    signal_date_max: str | None = None

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
            "orphan_row_count": self.orphan_row_count,
            "canonical_row_count": self.canonical_row_count,
            "quarantined_row_count": self.quarantined_row_count,
            "deleted_row_count": self.deleted_row_count,
            "missing_columns": list(self.missing_columns),
            "date_range": {
                "signal_date_min": self.signal_date_min,
                "signal_date_max": self.signal_date_max,
            },
            "findings": [dict(f) for f in self.findings],
        }


def _default_clock() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepairSignalForwardLabelsUseCase:
    """Repair (quarantine + delete) orphan signal_forward_labels rows."""

    _ARTIFACT_TYPE = "signal_forward_labels_repair"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: SignalForwardLabelsRepairReader,
        repairer: SignalForwardLabelsRepairer,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._repairer = repairer
        self._clock = clock or _default_clock

    def execute(self, apply: bool = False) -> RepairSignalForwardLabelsResponse:
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
                source_unavailable_reason = SIGNAL_FORWARD_LABELS_TABLE_MISSING
            elif state.source_unavailable:
                source_unavailable_reason = state.source_unavailable_reason

        if source_unavailable_reason is not None:
            return RepairSignalForwardLabelsResponse(
                generated_at=generated_at,
                mode=mode,
                status="FAIL",
                source_available=False,
                source_unavailable_reason=source_unavailable_reason,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                missing_columns=state.missing_columns if not source_unavailable_reason.startswith("DATABASE_") else (),
                findings=[
                    {
                        "severity": "FAIL",
                        "code": "SOURCE_UNAVAILABLE",
                        "message": (
                            f"signal_forward_labels repair is not available: "
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
                    "code": "LINKAGE_COLUMN_MISSING",
                    "message": (
                        f"Required linkage column '{col}' does not exist. "
                    ),
                }
            )

        total = state.total_row_count
        orphan = state.orphan_row_count
        canonical = state.canonical_row_count

        if orphan == 0:
            findings.append(
                {
                    "severity": "INFO",
                    "code": "NO_ORPHAN_ROWS",
                    "message": "No orphan signal_forward_labels rows found.",
                }
            )
            return RepairSignalForwardLabelsResponse(
                generated_at=generated_at,
                mode=mode,
                status="PASS",
                source_available=True,
                source_unavailable_reason=None,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                total_row_count=total,
                orphan_row_count=0,
                canonical_row_count=canonical,
                quarantined_row_count=0,
                deleted_row_count=0,
                missing_columns=state.missing_columns,
                signal_date_min=state.signal_date_min,
                signal_date_max=state.signal_date_max,
                findings=findings,
            )

        if dry_run:
            findings.append(
                {
                    "severity": "FAIL",
                    "code": "ORPHAN_LABEL_ROWS_PRESENT",
                    "message": (
                        f"{orphan} of {total} signal_forward_labels row(s) "
                        f"are orphaned (no matching candidate_observations "
                        f"row). Run with --apply to quarantine them."
                    ),
                }
            )
            return RepairSignalForwardLabelsResponse(
                generated_at=generated_at,
                mode=mode,
                status="FAIL",
                source_available=True,
                source_unavailable_reason=None,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                total_row_count=total,
                orphan_row_count=orphan,
                canonical_row_count=canonical,
                quarantined_row_count=0,
                deleted_row_count=0,
                missing_columns=state.missing_columns,
                signal_date_min=state.signal_date_min,
                signal_date_max=state.signal_date_max,
                findings=findings,
            )

        self._repairer.ensure_quarantine_table()
        quarantined, deleted = self._repairer.quarantine_and_delete_orphans(repair_run_id)

        is_success = quarantined == deleted == orphan
        status = "PASS" if is_success else "FAIL"
        findings.append(
            {
                "severity": "INFO" if is_success else "FAIL",
                "code": (
                    "ORPHAN_LABELS_QUARANTINED"
                    if is_success
                    else "QUARANTINE_COUNT_MISMATCH"
                ),
                "message": (
                    f"Quarantined and deleted {quarantined} of {orphan} "
                    f"orphan label row(s)."
                    if is_success
                    else (
                        f"Expected to quarantine {orphan} orphan label "
                        f"row(s), quarantined {quarantined} and deleted "
                        f"{deleted}."
                    )
                ),
            }
        )

        return RepairSignalForwardLabelsResponse(
            generated_at=generated_at,
            mode=mode,
            status=status,
            source_available=True,
            source_unavailable_reason=None,
            dry_run=dry_run,
            repair_run_id=repair_run_id,
            total_row_count=total,
            orphan_row_count=orphan,
            canonical_row_count=canonical,
            quarantined_row_count=quarantined,
            deleted_row_count=deleted,
            missing_columns=state.missing_columns,
            signal_date_min=state.signal_date_min,
            signal_date_max=state.signal_date_max,
            findings=findings,
        )
