"""
DTOs for the read-only source reconciliation audit (DQ-001B core tables,
DQ-001D enrichment/source-context tables).

Extracted from audit_source_reconciliation_use_case.py so that file can stay
a thin orchestrator (AI_AGENT_CHECKLIST.md file-size rules: >700 LOC requires
an extraction plan before adding new behavior). Raw*Observation dataclasses
are read-only facts produced by infrastructure readers; Finding/CheckResult/
Response are the audit's public output contract.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

_STATUS_ORDER = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}
_MAX_SAMPLE_ROWS = 10


def worse_status(a: str, b: str) -> str:
    return b if _STATUS_ORDER.get(b, 0) > _STATUS_ORDER.get(a, 0) else a


def aggregate_status(values: Iterable[str]) -> str:
    status = "PASS"
    for value in values:
        if value in ("FAIL", "WARN"):
            status = worse_status(status, value)
    return status


@dataclass(frozen=True)
class SourceReconciliationFinding:
    severity: str  # "FAIL" | "WARN" | "INFO"
    code: str
    table: str
    field: str | None
    message: str
    impact: str
    sample_rows: tuple[dict, ...] = ()
    row_count: int | None = None
    mismatch_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "table": self.table,
            "field": self.field,
            "message": self.message,
            "impact": self.impact,
            "sample_rows": [dict(r) for r in self.sample_rows[:_MAX_SAMPLE_ROWS]],
            "row_count": self.row_count,
            "mismatch_count": self.mismatch_count,
        }


@dataclass(frozen=True)
class SourceReconciliationCheckResult:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    tables: tuple[str, ...]
    checked_row_count: int | None
    mismatch_count: int | None
    summary: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "tables": list(self.tables),
            "checked_row_count": self.checked_row_count,
            "mismatch_count": self.mismatch_count,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class AuditSourceReconciliationResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    status: str  # "PASS" | "WARN" | "FAIL"
    checks: tuple[SourceReconciliationCheckResult, ...]
    findings: tuple[SourceReconciliationFinding, ...]

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# DQ-001B: core market/broker raw observations.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawCandlesOhlcObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    price_columns_present: bool = True
    volume_column_present: bool = True
    invalid_ohlc_count: int = 0
    invalid_ohlc_samples: tuple[dict, ...] = ()
    negative_volume_count: int = 0
    negative_volume_samples: tuple[dict, ...] = ()
    unknown_provenance_count: int = 0
    unknown_provenance_samples: tuple[dict, ...] = ()
    source_distribution: dict = field(default_factory=dict)
    volume_unit_distribution: dict = field(default_factory=dict)
    price_adjustment_policy_distribution: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RawBrokerSummariesObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    value_columns_present: bool = True
    negative_value_count: int = 0
    negative_value_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawBrokerDailyFlowObservation:
    exists: bool
    row_count: int = 0
    identity_columns_present: bool = True
    value_columns_present: bool = True
    negative_value_count: int = 0
    negative_value_samples: tuple[dict, ...] = ()
    net_mismatch_count: int = 0
    net_mismatch_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    broker_code_count_min: int | None = None
    broker_code_count_max: int | None = None
    broker_code_count_avg: float | None = None
    distinct_broker_code_total: int | None = None


@dataclass(frozen=True)
class RawForeignFlowReconciliationObservation:
    foreign_flow_points_exists: bool
    foreign_flow_points_schema_sufficient: bool
    total_row_count: int = 0
    matched_row_count: int = 0
    unmatched_row_count: int = 0
    mismatch_count: int = 0
    mismatch_samples: tuple[dict, ...] = ()
    foreign_flow_snapshots_exists: bool = False


# ---------------------------------------------------------------------------
# DQ-001D: enrichment/source-context raw observations.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSeasonalityObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    invalid_source_count: int = 0
    invalid_source_samples: tuple[dict, ...] = ()
    null_fetched_at_count: int = 0
    null_fetched_at_samples: tuple[dict, ...] = ()
    null_fetched_month_count: int = 0
    fetched_month_mismatch_count: int = 0
    fetched_month_mismatch_samples: tuple[dict, ...] = ()
    all_metrics_null_count: int = 0


@dataclass(frozen=True)
class RawPitCacheObservation:
    """Shared shape for company_fundamentals/analyst_cache/forward_estimates_cache:
    a (ticker, fetched_date) identity cache with metric columns that may
    legitimately all be null."""

    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    missing_identity_count: int = 0
    missing_identity_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    all_metrics_null_count: int = 0
    all_metrics_null_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawInsiderCacheObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    missing_identity_count: int = 0
    missing_identity_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawCorporateActionLinkageObservation:
    events_exists: bool
    event_dates_exists: bool
    events_schema_sufficient: bool = True
    events_missing_columns: tuple[str, ...] = ()
    event_dates_schema_sufficient: bool = True
    event_dates_missing_columns: tuple[str, ...] = ()
    events_row_count: int = 0
    event_dates_row_count: int = 0
    orphan_date_rows_count: int = 0
    orphan_date_rows_samples: tuple[dict, ...] = ()
    events_without_dates_count: int = 0
    events_without_dates_samples: tuple[dict, ...] = ()
    null_event_date_count: int = 0
    null_event_date_samples: tuple[dict, ...] = ()
    null_date_role_count: int = 0


@dataclass(frozen=True)
class RawTickerNotationObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    missing_provenance_count: int = 0
    missing_provenance_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawStockMetaObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    missing_identity_count: int = 0
    missing_identity_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    both_sector_industry_null_count: int = 0
    both_sector_industry_null_samples: tuple[dict, ...] = ()


# ---------------------------------------------------------------------------
# DQ-001E: signal-artifact and market-context raw observations.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawCandidateObservationIdentityObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    canonical_row_count: int = 0
    legacy_row_count: int = 0
    canonical_missing_identity_count: int = 0
    canonical_missing_identity_samples: tuple[dict, ...] = ()
    duplicate_canonical_identity_count: int = 0
    duplicate_canonical_identity_samples: tuple[dict, ...] = ()
    invalid_payload_json_count: int = 0
    invalid_payload_json_samples: tuple[dict, ...] = ()
    payload_missing_schema_marker_count: int = 0
    payload_missing_schema_marker_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawSignalForwardLabelsLinkageObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    missing_identity_count: int = 0
    missing_identity_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    invalid_fingerprint_json_count: int = 0
    invalid_fingerprint_json_samples: tuple[dict, ...] = ()
    linkage_provable: bool = False
    orphan_linkage_count: int = 0
    orphan_linkage_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawMarketContextSnapshotObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    invalid_regime_count: int = 0
    invalid_regime_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    missing_provenance_count: int = 0
    missing_provenance_samples: tuple[dict, ...] = ()
    invalid_factors_json_count: int = 0
    invalid_factors_json_samples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RawRegimeObservationsObservation:
    exists: bool
    row_count: int = 0
    schema_sufficient: bool = True
    missing_columns: tuple[str, ...] = ()
    invalid_regime_count: int = 0
    invalid_regime_samples: tuple[dict, ...] = ()
    duplicate_identity_count: int = 0
    duplicate_identity_samples: tuple[dict, ...] = ()
    null_confidence_or_stability_count: int = 0
    invalid_detection_inputs_json_count: int = 0
    invalid_detection_inputs_json_samples: tuple[dict, ...] = ()
