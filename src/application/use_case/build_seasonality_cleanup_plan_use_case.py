"""
Read-only DQ-001G seasonality cleanup plan.

Scans `seasonality_cache` and identifies rows with unusable provenance or
payload — the same rows DQ-001F's `StockbitSeasonalityProvider._read_cache()`
already refuses to serve at runtime. This use case does not repair,
quarantine, or delete anything: it is a dry-run plan only, listing exactly
which rows are invalid and why, for a human/future repair task to act on.

Row invalidity policy (business rule, kept here — not in the reader):
  - INVALID_SOURCE: source is null, empty, or case-insensitive "unknown"
  - MISSING_FETCHED_AT: fetched_at is null or empty
  - MALFORMED_FETCHED_AT: fetched_at is set but not ISO-parseable
  - ALL_METRICS_NULL: every one of avg_return_pct/win_rate_pct/
    positive_years/total_years/back_years is null (a row with only some
    metrics null is not flagged here — DQ-001F's runtime guard already
    rejects those independently; this plan targets clearly-bad artifacts)

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol

REASON_INVALID_SOURCE = "INVALID_SOURCE"
REASON_MISSING_FETCHED_AT = "MISSING_FETCHED_AT"
REASON_MALFORMED_FETCHED_AT = "MALFORMED_FETCHED_AT"
REASON_ALL_METRICS_NULL = "ALL_METRICS_NULL"

_ALL_REASON_CODES = (
    REASON_INVALID_SOURCE,
    REASON_MISSING_FETCHED_AT,
    REASON_MALFORMED_FETCHED_AT,
    REASON_ALL_METRICS_NULL,
)


@dataclass(frozen=True)
class RawSeasonalityCacheRow:
    """One raw, uninterpreted seasonality_cache row."""

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


@dataclass(frozen=True)
class RawSeasonalityCacheObservation:
    """Read-only observed facts for the whole seasonality_cache table."""

    exists: bool
    rows: tuple[RawSeasonalityCacheRow, ...] = ()


class SeasonalityCleanupPlanReader(Protocol):
    """Read-only observer of seasonality_cache. Must never mutate the database."""

    def database_exists(self) -> bool: ...

    def observe_seasonality_cache(self) -> RawSeasonalityCacheObservation: ...


@dataclass(frozen=True)
class SeasonalityCleanupPlanRow:
    """One invalid seasonality_cache row and why it is invalid."""

    ticker: str
    year: int
    month: int
    fetched_month: str | None
    fetched_at: str | None
    source: str | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "year": self.year,
            "month": self.month,
            "fetched_month": self.fetched_month,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SeasonalityCleanupPlanResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    table: str
    status: str  # "PASS" | "FAIL"
    invalid_row_count: int
    invalid_reason_counts: dict[str, int]
    dry_run: bool
    proposed_action: str
    rows: tuple[SeasonalityCleanupPlanRow, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "table": self.table,
            "status": self.status,
            "invalid_row_count": self.invalid_row_count,
            "invalid_reason_counts": dict(self.invalid_reason_counts),
            "dry_run": self.dry_run,
            "proposed_action": self.proposed_action,
            "rows": [r.to_dict() for r in self.rows],
        }


class BuildSeasonalityCleanupPlanUseCase:
    """Evaluate a read-only, dry-run cleanup plan for invalid seasonality_cache rows."""

    _ARTIFACT_TYPE = "seasonality_cleanup_plan"
    _SCHEMA_VERSION = 1
    _TABLE = "seasonality_cache"
    _PROPOSED_ACTION = "DELETE_INVALID_SEASONALITY_ROW"

    def __init__(
        self,
        reader: SeasonalityCleanupPlanReader,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._clock = clock or _default_clock

    def execute(self) -> SeasonalityCleanupPlanResponse:
        invalid_rows: list[SeasonalityCleanupPlanRow] = []
        reason_counts: dict[str, int] = {code: 0 for code in _ALL_REASON_CODES}

        if self._reader.database_exists():
            observation = self._reader.observe_seasonality_cache()
            if observation.exists:
                for raw in observation.rows:
                    reasons = _classify(raw)
                    if not reasons:
                        continue
                    for reason in reasons:
                        reason_counts[reason] += 1
                    invalid_rows.append(
                        SeasonalityCleanupPlanRow(
                            ticker=raw.ticker,
                            year=raw.year,
                            month=raw.month,
                            fetched_month=raw.fetched_month,
                            fetched_at=raw.fetched_at,
                            source=raw.source,
                            reasons=reasons,
                        )
                    )

        status = "PASS" if not invalid_rows else "FAIL"

        return SeasonalityCleanupPlanResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            table=self._TABLE,
            status=status,
            invalid_row_count=len(invalid_rows),
            invalid_reason_counts=reason_counts,
            dry_run=True,
            proposed_action=self._PROPOSED_ACTION,
            rows=tuple(invalid_rows),
        )


def _classify(row: RawSeasonalityCacheRow) -> tuple[str, ...]:
    reasons: list[str] = []

    source = row.source
    if not source or source.strip().lower() == "unknown":
        reasons.append(REASON_INVALID_SOURCE)

    fetched_at = row.fetched_at
    if not fetched_at:
        reasons.append(REASON_MISSING_FETCHED_AT)
    else:
        try:
            datetime.fromisoformat(fetched_at)
        except (TypeError, ValueError):
            reasons.append(REASON_MALFORMED_FETCHED_AT)

    metrics = (
        row.avg_return_pct,
        row.win_rate_pct,
        row.positive_years,
        row.total_years,
        row.back_years,
    )
    if all(m is None for m in metrics):
        reasons.append(REASON_ALL_METRICS_NULL)

    return tuple(reasons)


def _default_clock() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat()
