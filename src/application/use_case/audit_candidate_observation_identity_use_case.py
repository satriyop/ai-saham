"""
Read-only DQ-001I candidate_observations identity audit.

Scans `candidate_observations` and reports exactly how many rows are legacy
(empty config_hash), canonical (non-empty config_hash), whether the latest
snapshot depends on legacy rows, and whether duplicate identity groups exist
among canonical rows.  Report command only — never mutates the database.

Legacy definition: config_hash is NULL or empty after trim.
Canonical definition: config_hash is non-empty after trim.

Duplicate identity group: canonical rows grouped by
(ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)
with COUNT(*) > 1.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol

DATABASE_MISSING = "DATABASE_MISSING"
CANDIDATE_OBSERVATIONS_TABLE_MISSING = "CANDIDATE_OBSERVATIONS_TABLE_MISSING"


@dataclass(frozen=True)
class RawCandidateObservationIdentityData:
    """Raw aggregate facts about candidate_observations returned by the reader.

    The reader never classifies or evaluates — it only collects SQL aggregates
    and returns them uninterpreted.
    """

    exists: bool
    total_row_count: int = 0
    canonical_row_count: int = 0
    legacy_row_count: int = 0
    snapshot_date_min: str | None = None
    snapshot_date_max: str | None = None
    captured_at_min: str | None = None
    captured_at_max: str | None = None
    missing_identity_counts: dict[str, int] = field(default_factory=dict)
    workflow_counts: list[dict] = field(default_factory=list)
    window_session_counts: list[dict] = field(default_factory=list)
    legacy_by_snapshot_date: list[dict] = field(default_factory=list)
    duplicate_identity_group_count: int = 0
    duplicate_identity_row_count: int = 0
    latest_readiness_dependency: dict = field(default_factory=dict)
    missing_columns: tuple[str, ...] = ()


class CandidateObservationIdentityReader(Protocol):
    """Read-only observer of candidate_observations. Must never mutate the database."""

    def database_exists(self) -> bool: ...

    def observe_candidate_observation_identity(self) -> RawCandidateObservationIdentityData: ...


@dataclass(frozen=True)
class CandidateObservationIdentityAuditResponse:
    artifact_type: str = "candidate_observation_identity_audit"
    schema_version: int = 1
    generated_at: str = ""
    table: str = "candidate_observations"
    status: str = "FAIL"
    source_available: bool = True
    source_unavailable_reason: str | None = None

    total_row_count: int = 0
    canonical_row_count: int = 0
    legacy_row_count: int = 0
    legacy_ratio: float = 0.0

    snapshot_date_min: str | None = None
    snapshot_date_max: str | None = None
    captured_at_min: str | None = None
    captured_at_max: str | None = None

    missing_identity_counts: dict[str, int] = field(default_factory=dict)
    workflow_counts: list[dict] = field(default_factory=list)
    window_session_counts: list[dict] = field(default_factory=list)
    legacy_by_snapshot_date: list[dict] = field(default_factory=list)

    duplicate_identity_group_count: int = 0
    duplicate_identity_row_count: int = 0

    latest_readiness_dependency: dict = field(default_factory=dict)

    recommendation: str = "SOURCE_UNAVAILABLE"
    findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "table": self.table,
            "status": self.status,
            "source_available": self.source_available,
            "source_unavailable_reason": self.source_unavailable_reason,
            "total_row_count": self.total_row_count,
            "canonical_row_count": self.canonical_row_count,
            "legacy_row_count": self.legacy_row_count,
            "legacy_ratio": self.legacy_ratio,
            "snapshot_date_min": self.snapshot_date_min,
            "snapshot_date_max": self.snapshot_date_max,
            "captured_at_min": self.captured_at_min,
            "captured_at_max": self.captured_at_max,
            "missing_identity_counts": dict(self.missing_identity_counts),
            "workflow_counts": self.workflow_counts,
            "window_session_counts": self.window_session_counts,
            "legacy_by_snapshot_date": self.legacy_by_snapshot_date,
            "duplicate_identity_group_count": self.duplicate_identity_group_count,
            "duplicate_identity_row_count": self.duplicate_identity_row_count,
            "latest_readiness_dependency": dict(self.latest_readiness_dependency),
            "recommendation": self.recommendation,
            "findings": [dict(f) for f in self.findings],
        }


class AuditCandidateObservationIdentityUseCase:
    _ARTIFACT_TYPE = "candidate_observation_identity_audit"
    _SCHEMA_VERSION = 1
    _TABLE = "candidate_observations"

    def __init__(
        self,
        reader: CandidateObservationIdentityReader,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._clock = clock or _default_clock

    def execute(self) -> CandidateObservationIdentityAuditResponse:
        generated_at = self._clock()
        findings: list[dict] = []

        source_unavailable_reason: str | None = None
        if not self._reader.database_exists():
            source_unavailable_reason = DATABASE_MISSING
        else:
            data = self._reader.observe_candidate_observation_identity()
            if not data.exists:
                source_unavailable_reason = CANDIDATE_OBSERVATIONS_TABLE_MISSING

        if source_unavailable_reason is not None:
            return CandidateObservationIdentityAuditResponse(
                generated_at=generated_at,
                status="FAIL",
                source_available=False,
                source_unavailable_reason=source_unavailable_reason,
                missing_identity_counts={
                    "config_hash": 0,
                    "workflow": 0,
                    "window_sessions": 0,
                    "data_as_of_date": 0,
                },
                recommendation="SOURCE_UNAVAILABLE",
                findings=[
                    {
                        "severity": "FAIL",
                        "code": "SOURCE_UNAVAILABLE",
                        "message": f"candidate_observations is not accessible: {source_unavailable_reason}",
                    }
                ],
            )

        total = data.total_row_count
        canonical = data.canonical_row_count
        legacy = data.legacy_row_count
        legacy_ratio = round(legacy / total, 4) if total > 0 else 0.0

        missing_identity_counts = dict(data.missing_identity_counts)
        workflow_counts = list(data.workflow_counts)
        window_session_counts = list(data.window_session_counts)
        legacy_by_snapshot_date = list(data.legacy_by_snapshot_date)
        duplicate_group_count = data.duplicate_identity_group_count
        duplicate_row_count = data.duplicate_identity_row_count
        latest_dep = dict(data.latest_readiness_dependency)

        for col in data.missing_columns:
            findings.append({
                "severity": "WARN",
                "code": "IDENTITY_COLUMN_MISSING",
                "message": f"Identity column '{col}' does not exist in the table. "
                f"All {total} rows are counted as missing for this field.",
            })

        if total == 0:
            return CandidateObservationIdentityAuditResponse(
                generated_at=generated_at,
                status="PASS",
                source_available=True,
                total_row_count=0,
                legacy_row_count=0,
                canonical_row_count=0,
                legacy_ratio=0.0,
                missing_identity_counts=missing_identity_counts,
                workflow_counts=workflow_counts,
                window_session_counts=window_session_counts,
                legacy_by_snapshot_date=legacy_by_snapshot_date,
                duplicate_identity_group_count=duplicate_group_count,
                duplicate_identity_row_count=duplicate_row_count,
                latest_readiness_dependency=latest_dep,
                recommendation="NO_ACTION",
                findings=[
                    {
                        "severity": "INFO",
                        "code": "NO_CANDIDATE_OBSERVATIONS",
                        "message": "candidate_observations table exists but contains 0 rows.",
                    }
                ],
            )

        if duplicate_group_count > 0:
            findings.append({
                "severity": "WARN",
                "code": "DUPLICATE_CANONICAL_IDENTITY_GROUPS",
                "message": f"{duplicate_row_count} canonical row(s) belong to "
                f"{duplicate_group_count} duplicate identity group(s).",
            })

        depends_on_legacy = latest_dep.get("depends_on_legacy", False)

        if legacy > 0 and depends_on_legacy:
            status = "FAIL"
            recommendation = "REBUILD_REQUIRED"
            findings.append({
                "severity": "FAIL",
                "code": "LATEST_READINESS_DEPENDS_ON_LEGACY_IDENTITY",
                "message": f"{latest_dep.get('latest_legacy_rows', 0)} of "
                f"{latest_dep.get('latest_total_rows', 0)} row(s) on the latest snapshot date "
                f"({latest_dep.get('latest_snapshot_date', 'N/A')}) are legacy. "
                f"Readiness/replay/tuning depend on legacy identity.",
            })
        elif legacy > 0:
            status = "WARN"
            recommendation = "QUARANTINE_SAFE"
            findings.append({
                "severity": "WARN",
                "code": "HISTORICAL_LEGACY_ROWS_PRESENT",
                "message": f"{legacy} of {total} row(s) are legacy but the latest snapshot "
                f"({latest_dep.get('latest_snapshot_date', 'N/A')}) has "
                f"{latest_dep.get('latest_canonical_rows', 0)} "
                f"canonical row(s). Historical legacy rows can be quarantined safely.",
            })
        else:
            status = "PASS"
            recommendation = "NO_ACTION"

        if duplicate_group_count > 0 and status == "PASS":
            status = "WARN"

        return CandidateObservationIdentityAuditResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=generated_at,
            table=self._TABLE,
            status=status,
            source_available=True,
            source_unavailable_reason=None,
            total_row_count=total,
            canonical_row_count=canonical,
            legacy_row_count=legacy,
            legacy_ratio=legacy_ratio,
            snapshot_date_min=data.snapshot_date_min,
            snapshot_date_max=data.snapshot_date_max,
            captured_at_min=data.captured_at_min,
            captured_at_max=data.captured_at_max,
            missing_identity_counts=missing_identity_counts,
            workflow_counts=workflow_counts,
            window_session_counts=window_session_counts,
            legacy_by_snapshot_date=legacy_by_snapshot_date,
            duplicate_identity_group_count=duplicate_group_count,
            duplicate_identity_row_count=duplicate_row_count,
            latest_readiness_dependency=latest_dep,
            recommendation=recommendation,
            findings=findings,
        )


def _default_clock() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat()
