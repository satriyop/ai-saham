"""
DQ-001H — deterministic seasonality_cache quarantine repair command.

Reuses the same row-invalidity classification from
BuildSeasonalityCleanupPlanUseCase (DQ-001G).  Adds a repair workflow that
either dry-reports or transactionally quarantines+deletes invalid rows.

Layer: Application
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from src.application.use_case.build_seasonality_cleanup_plan_use_case import (
    REASON_ALL_METRICS_NULL,
    REASON_DATABASE_MISSING,
    REASON_INVALID_SOURCE,
    REASON_MALFORMED_FETCHED_AT,
    REASON_MISSING_FETCHED_AT,
    REASON_SEASONALITY_CACHE_TABLE_MISSING,
    SeasonalityCleanupPlanReader,
    _classify,
)

_ROW_REASON_CODES = (
    REASON_INVALID_SOURCE,
    REASON_MISSING_FETCHED_AT,
    REASON_MALFORMED_FETCHED_AT,
    REASON_ALL_METRICS_NULL,
)

_TABLE_LEVEL_REASON_CODES = (
    REASON_DATABASE_MISSING,
    REASON_SEASONALITY_CACHE_TABLE_MISSING,
)

_ALL_REASON_CODES = _ROW_REASON_CODES + _TABLE_LEVEL_REASON_CODES


@dataclass(frozen=True)
class SeasonalityCacheRepairRow:
    """Full seasonality_cache row data with quarantine reasons."""

    ticker: str
    year: int
    month: int
    fetched_month: str | None
    fetched_at: str | None
    source: str | None
    avg_return_pct: float | None
    win_rate_pct: float | None
    positive_years: int | None
    total_years: int | None
    back_years: int | None
    reasons: tuple[str, ...]


class SeasonalityCacheRepairer(Protocol):
    """Mutating port for the seasonality_cache quarantine/delete workflow."""

    def ensure_quarantine_table(self) -> None: ...

    def quarantine_and_delete(
        self,
        rows: list[SeasonalityCacheRepairRow],
        repair_run_id: str,
    ) -> int: ...


@dataclass(frozen=True)
class RepairSeasonalityCacheResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    mode: str  # "DRY_RUN" | "APPLY"
    status: str  # "PASS" | "FAIL"
    source_available: bool
    source_unavailable_reason: str | None
    invalid_row_count: int
    quarantined_row_count: int
    deleted_row_count: int
    dry_run: bool
    repair_run_id: str
    reason_counts: dict[str, int]
    rows: tuple[SeasonalityCacheRepairRow, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "mode": self.mode,
            "status": self.status,
            "source_available": self.source_available,
            "source_unavailable_reason": self.source_unavailable_reason,
            "invalid_row_count": self.invalid_row_count,
            "quarantined_row_count": self.quarantined_row_count,
            "deleted_row_count": self.deleted_row_count,
            "dry_run": self.dry_run,
            "repair_run_id": self.repair_run_id,
            "reason_counts": dict(self.reason_counts),
            "rows": [_repair_row_to_dict(r) for r in self.rows],
        }


def _repair_row_to_dict(row: SeasonalityCacheRepairRow) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "year": row.year,
        "month": row.month,
        "fetched_month": row.fetched_month,
        "fetched_at": row.fetched_at,
        "source": row.source,
        "avg_return_pct": row.avg_return_pct,
        "win_rate_pct": row.win_rate_pct,
        "positive_years": row.positive_years,
        "total_years": row.total_years,
        "back_years": row.back_years,
        "reasons": list(row.reasons),
    }


def _default_clock() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepairSeasonalityCacheUseCase:
    """Repair (quarantine + delete) invalid seasonality_cache rows."""

    _ARTIFACT_TYPE = "seasonality_cache_repair"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: SeasonalityCleanupPlanReader,
        repairer: SeasonalityCacheRepairer,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._repairer = repairer
        self._clock = clock or _default_clock

    def execute(self, dry_run: bool = True) -> RepairSeasonalityCacheResponse:
        repair_run_id = str(uuid.uuid4())
        generated_at = self._clock()

        reason_counts: dict[str, int] = {code: 0 for code in _ALL_REASON_CODES}

        source_unavailable_reason: str | None = None
        if not self._reader.database_exists():
            source_unavailable_reason = REASON_DATABASE_MISSING
        else:
            observation = self._reader.observe_seasonality_cache()
            if not observation.exists:
                source_unavailable_reason = REASON_SEASONALITY_CACHE_TABLE_MISSING
            else:
                repair_rows = self._collect_invalid_rows(observation.rows, reason_counts)

        source_available = source_unavailable_reason is None
        if source_unavailable_reason is not None:
            reason_counts[source_unavailable_reason] = 1
            return RepairSeasonalityCacheResponse(
                artifact_type=self._ARTIFACT_TYPE,
                schema_version=self._SCHEMA_VERSION,
                generated_at=generated_at,
                mode="DRY_RUN" if dry_run else "APPLY",
                status="FAIL",
                source_available=source_available,
                source_unavailable_reason=source_unavailable_reason,
                invalid_row_count=0,
                quarantined_row_count=0,
                deleted_row_count=0,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                reason_counts=reason_counts,
                rows=(),
            )

        if not repair_rows:
            return RepairSeasonalityCacheResponse(
                artifact_type=self._ARTIFACT_TYPE,
                schema_version=self._SCHEMA_VERSION,
                generated_at=generated_at,
                mode="DRY_RUN" if dry_run else "APPLY",
                status="PASS",
                source_available=True,
                source_unavailable_reason=None,
                invalid_row_count=0,
                quarantined_row_count=0,
                deleted_row_count=0,
                dry_run=dry_run,
                repair_run_id=repair_run_id,
                reason_counts=reason_counts,
                rows=(),
            )

        quarantined_count = 0
        deleted_count = 0
        if not dry_run:
            self._repairer.ensure_quarantine_table()
            affected = self._repairer.quarantine_and_delete(repair_rows, repair_run_id)
            quarantined_count = affected
            deleted_count = affected

        is_apply_success = not dry_run and quarantined_count == len(repair_rows)
        status = "PASS" if is_apply_success else "FAIL"

        return RepairSeasonalityCacheResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=generated_at,
            mode="DRY_RUN" if dry_run else "APPLY",
            status=status,
            source_available=True,
            source_unavailable_reason=None,
            invalid_row_count=len(repair_rows),
            quarantined_row_count=quarantined_count,
            deleted_row_count=deleted_count,
            dry_run=dry_run,
            repair_run_id=repair_run_id,
            reason_counts=reason_counts,
            rows=tuple(repair_rows),
        )

    def _collect_invalid_rows(
        self,
        raw_rows: tuple,
        reason_counts: dict[str, int],
    ) -> list[SeasonalityCacheRepairRow]:
        repair_rows: list[SeasonalityCacheRepairRow] = []
        for raw in raw_rows:
            reasons = _classify(raw)
            if not reasons:
                continue
            for reason in reasons:
                reason_counts[reason] += 1
            repair_rows.append(
                SeasonalityCacheRepairRow(
                    ticker=raw.ticker,
                    year=raw.year,
                    month=raw.month,
                    fetched_month=raw.fetched_month,
                    fetched_at=raw.fetched_at,
                    source=raw.source,
                    avg_return_pct=raw.avg_return_pct,
                    win_rate_pct=raw.win_rate_pct,
                    positive_years=raw.positive_years,
                    total_years=raw.total_years,
                    back_years=raw.back_years,
                    reasons=reasons,
                )
            )
        return repair_rows
