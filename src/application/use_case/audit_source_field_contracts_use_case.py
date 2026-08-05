"""
Read-only executable source-field contract audit (DQ-001A).

Verifies that core market/broker/observation/label tables satisfy their
declared source-field contracts (semantics, units, grain, null handling,
point-in-time support). Never repairs, rebuilds, quarantines, or generates
observations/labels — read-only findings only.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

_STATUS_ORDER = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}


def _worse(a: str, b: str) -> str:
    return b if _STATUS_ORDER.get(b, 0) > _STATUS_ORDER.get(a, 0) else a


def _aggregate_status(values: Iterable[str]) -> str:
    status = "PASS"
    for value in values:
        if value in ("FAIL", "WARN"):
            status = _worse(status, value)
    return status


@dataclass(frozen=True)
class SourceFieldContract:
    """Static, injected contract describing what a source field should mean."""

    field: str
    required: bool
    semantic_name: str
    source_owner: str
    unit: str
    sign_convention: str | None
    aggregation: str
    grain: str
    temporal_meaning: str
    null_semantics: str
    point_in_time_support: str  # "HISTORICAL" | "CURRENT_ONLY" | "UNVERIFIED"
    null_policy: str = "fail"  # "fail" | "warn" | "ignore"
    invalid_values: frozenset[str] = frozenset()
    invalid_value_policy: str = "fail"  # "fail" | "warn"


@dataclass(frozen=True)
class RawFieldObservation:
    """Read-only observed facts for one field, with no interpretation applied."""

    field: str
    exists: bool
    null_count: int | None = None
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    invalid_value_count: int | None = None


@dataclass(frozen=True)
class RawTableObservation:
    """Read-only observed facts for one table."""

    table: str
    exists: bool
    row_count: int | None = None
    fields: tuple[RawFieldObservation, ...] = ()
    special_checks: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceFieldContractResult:
    field: str
    exists: bool
    required: bool
    semantic_name: str
    source_owner: str
    unit: str
    sign_convention: str | None
    aggregation: str
    grain: str
    temporal_meaning: str
    null_semantics: str
    point_in_time_support: str
    observed_null_count: int | None
    observed_distinct_count: int | None
    observed_min: str | None
    observed_max: str | None
    status: str  # "PASS" | "WARN" | "FAIL"
    issue: str | None

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "exists": self.exists,
            "required": self.required,
            "semantic_name": self.semantic_name,
            "source_owner": self.source_owner,
            "unit": self.unit,
            "sign_convention": self.sign_convention,
            "aggregation": self.aggregation,
            "grain": self.grain,
            "temporal_meaning": self.temporal_meaning,
            "null_semantics": self.null_semantics,
            "point_in_time_support": self.point_in_time_support,
            "observed_null_count": self.observed_null_count,
            "observed_distinct_count": self.observed_distinct_count,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "status": self.status,
            "issue": self.issue,
        }


@dataclass(frozen=True)
class SourceTableContractResult:
    table: str
    exists: bool
    row_count: int | None
    contract_status: str  # "PASS" | "WARN" | "FAIL"
    fields: tuple[SourceFieldContractResult, ...]

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "exists": self.exists,
            "row_count": self.row_count,
            "contract_status": self.contract_status,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass(frozen=True)
class SourceContractFinding:
    severity: str  # "FAIL" | "WARN" | "INFO"
    code: str
    table: str
    field: str | None
    message: str
    impact: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "table": self.table,
            "field": self.field,
            "message": self.message,
            "impact": self.impact,
        }


@dataclass(frozen=True)
class AuditSourceFieldContractsResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    tables: tuple[SourceTableContractResult, ...]
    findings: tuple[SourceContractFinding, ...]
    status: str  # "PASS" | "WARN" | "FAIL"

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "tables": [t.to_dict() for t in self.tables],
            "findings": [f.to_dict() for f in self.findings],
            "status": self.status,
        }


class SourceFieldContractReader(Protocol):
    """Read-only observer of table/field facts. Must never mutate the database."""

    def database_exists(self) -> bool: ...

    def observe_table(self, table: str) -> RawTableObservation: ...


class SourceFieldContractCatalog(Protocol):
    """Static, deterministic contract catalog for audited tables."""

    def tables(self) -> tuple[str, ...]: ...

    def contracts_for_table(self, table: str) -> tuple[SourceFieldContract, ...]: ...


class AuditSourceFieldContractsUseCase:
    """Evaluate executable source-field contracts for core tables (DQ-001A)."""

    _ARTIFACT_TYPE = "source_field_contract_audit"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: SourceFieldContractReader,
        catalog: SourceFieldContractCatalog,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._catalog = catalog
        self._clock = clock or _default_clock

    def execute(self) -> AuditSourceFieldContractsResponse:
        if not self._reader.database_exists():
            finding = SourceContractFinding(
                severity="FAIL",
                code="DATABASE_MISSING",
                table="",
                field=None,
                message="SQLite database does not exist.",
                impact="No source-field contracts can be verified.",
            )
            return AuditSourceFieldContractsResponse(
                artifact_type=self._ARTIFACT_TYPE,
                schema_version=self._SCHEMA_VERSION,
                generated_at=self._clock(),
                tables=(),
                findings=(finding,),
                status="FAIL",
            )

        tables: list[SourceTableContractResult] = []
        findings: list[SourceContractFinding] = []
        for table in self._catalog.tables():
            raw = self._reader.observe_table(table)
            contracts = self._catalog.contracts_for_table(table)
            table_result, table_findings = self._evaluate_table(table, raw, contracts)
            tables.append(table_result)
            findings.extend(table_findings)

        status = _aggregate_status(t.contract_status for t in tables)
        return AuditSourceFieldContractsResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            tables=tuple(tables),
            findings=tuple(findings),
            status=status,
        )

    def _evaluate_table(
        self,
        table: str,
        raw: RawTableObservation,
        contracts: tuple[SourceFieldContract, ...],
    ) -> tuple[SourceTableContractResult, tuple[SourceContractFinding, ...]]:
        if not raw.exists:
            finding = SourceContractFinding(
                severity="FAIL",
                code="MISSING_TABLE",
                table=table,
                field=None,
                message=f"{table} does not exist.",
                impact="Table cannot be used as canonical evidence.",
            )
            result = SourceTableContractResult(
                table=table, exists=False, row_count=None, contract_status="FAIL", fields=()
            )
            return result, (finding,)

        raw_fields_by_name = {f.field: f for f in raw.fields}
        field_results: list[SourceFieldContractResult] = []
        findings: list[SourceContractFinding] = []
        for contract in contracts:
            raw_field = raw_fields_by_name.get(contract.field)
            field_result, field_findings = self._evaluate_field(table, contract, raw_field)
            field_results.append(field_result)
            findings.extend(field_findings)

        table_findings = self._evaluate_table_specific_rules(table, raw)
        findings.extend(table_findings)

        contract_status = _aggregate_status(f.status for f in field_results)
        contract_status = _aggregate_status(
            [contract_status] + [f.severity for f in table_findings]
        )

        result = SourceTableContractResult(
            table=table,
            exists=True,
            row_count=raw.row_count,
            contract_status=contract_status,
            fields=tuple(field_results),
        )
        return result, tuple(findings)

    def _evaluate_field(
        self,
        table: str,
        contract: SourceFieldContract,
        raw_field: RawFieldObservation | None,
    ) -> tuple[SourceFieldContractResult, tuple[SourceContractFinding, ...]]:
        if raw_field is None or not raw_field.exists:
            status = "FAIL" if contract.required else "WARN"
            issue = "field missing from schema"
            findings: tuple[SourceContractFinding, ...] = ()
            if contract.required:
                findings = (
                    SourceContractFinding(
                        severity="FAIL",
                        code="MISSING_FIELD",
                        table=table,
                        field=contract.field,
                        message=f"{table}.{contract.field} does not exist.",
                        impact="Required source semantics cannot be verified.",
                    ),
                )
            result = SourceFieldContractResult(
                field=contract.field,
                exists=False,
                required=contract.required,
                semantic_name=contract.semantic_name,
                source_owner=contract.source_owner,
                unit=contract.unit,
                sign_convention=contract.sign_convention,
                aggregation=contract.aggregation,
                grain=contract.grain,
                temporal_meaning=contract.temporal_meaning,
                null_semantics=contract.null_semantics,
                point_in_time_support=contract.point_in_time_support,
                observed_null_count=None,
                observed_distinct_count=None,
                observed_min=None,
                observed_max=None,
                status=status,
                issue=issue,
            )
            return result, findings

        status = "PASS"
        issue: str | None = None
        findings = []

        if contract.null_policy == "fail" and raw_field.null_count:
            status = _worse(status, "FAIL")
            issue = f"{raw_field.null_count} null value(s) in required field"
            findings.append(
                SourceContractFinding(
                    severity="FAIL",
                    code="NULLS_IN_REQUIRED_FIELD",
                    table=table,
                    field=contract.field,
                    message=f"{table}.{contract.field} has {raw_field.null_count} null value(s).",
                    impact="Identity/date/source semantics cannot be trusted for affected rows.",
                )
            )
        elif contract.null_policy == "warn" and raw_field.null_count:
            status = _worse(status, "WARN")
            issue = f"{raw_field.null_count} null value(s) in optional field"
            findings.append(
                SourceContractFinding(
                    severity="WARN",
                    code="NULLS_IN_OPTIONAL_FIELD",
                    table=table,
                    field=contract.field,
                    message=f"{table}.{contract.field} has {raw_field.null_count} null value(s).",
                    impact="Coverage is incomplete for this field.",
                )
            )

        if contract.invalid_values and raw_field.invalid_value_count:
            invalid_status = contract.invalid_value_policy.upper()
            status = _worse(status, invalid_status)
            issue = f"{raw_field.invalid_value_count} row(s) with invalid/unknown value"
            findings.append(
                SourceContractFinding(
                    severity=invalid_status,
                    code="INVALID_FIELD_VALUE",
                    table=table,
                    field=contract.field,
                    message=(
                        f"{table}.{contract.field} has {raw_field.invalid_value_count} "
                        "row(s) with invalid/unknown value."
                    ),
                    impact="Provenance cannot be trusted for affected rows.",
                )
            )

        result = SourceFieldContractResult(
            field=contract.field,
            exists=True,
            required=contract.required,
            semantic_name=contract.semantic_name,
            source_owner=contract.source_owner,
            unit=contract.unit,
            sign_convention=contract.sign_convention,
            aggregation=contract.aggregation,
            grain=contract.grain,
            temporal_meaning=contract.temporal_meaning,
            null_semantics=contract.null_semantics,
            point_in_time_support=contract.point_in_time_support,
            observed_null_count=raw_field.null_count,
            observed_distinct_count=raw_field.distinct_count,
            observed_min=raw_field.min_value,
            observed_max=raw_field.max_value,
            status=status,
            issue=issue,
        )
        return result, tuple(findings)

    def _evaluate_table_specific_rules(
        self, table: str, raw: RawTableObservation
    ) -> tuple[SourceContractFinding, ...]:
        findings: list[SourceContractFinding] = []
        checks = raw.special_checks

        # ADR-068 removed the ``candidate_observations`` empty-``config_hash``
        # branch that used to sit here. That table was dropped 2026-07-27, so
        # the branch was unreachable, and ``config_hash`` is no longer written
        # to any observation payload.

        malformed_identity = checks.get("malformed_artifact_identity_count", 0)
        if malformed_identity:
            findings.append(
                SourceContractFinding(
                    severity="FAIL",
                    code="INVALID_ARTIFACT_IDENTITY",
                    table=table,
                    field=None,
                    message=(
                        f"{malformed_identity} row(s) have malformed or incomplete "
                        "artifact identity triplet."
                    ),
                    impact=(
                        "These rows have irreproducible or corrupt artifact identity; "
                        "they cannot be used for canonical evidence or replay."
                    ),
                )
            )

        if table == "signal_forward_labels":
            unavailable_missing_reason = checks.get("unavailable_without_reason_count", 0)
            if unavailable_missing_reason:
                findings.append(
                    SourceContractFinding(
                        severity="FAIL",
                        code="UNAVAILABLE_LABEL_MISSING_REASON",
                        table=table,
                        field="unavailable_reason",
                        message=(
                            f"{unavailable_missing_reason} label(s) marked UNAVAILABLE "
                            "without unavailable_reason."
                        ),
                        impact="Unavailable outcome cannot be explained or audited.",
                    )
                )
            incomplete_nulls = checks.get("complete_label_null_return_count", 0)
            if incomplete_nulls:
                findings.append(
                    SourceContractFinding(
                        severity="WARN",
                        code="COMPLETE_LABEL_MISSING_RETURN",
                        table=table,
                        field="close_return",
                        message=(
                            f"{incomplete_nulls} label(s) not marked UNAVAILABLE but "
                            "missing close_return."
                        ),
                        impact=(
                            "Return fields may be incomplete for labels claimed "
                            "complete; verify before use in readiness/tuning."
                        ),
                    )
                )

        if table == "broker_daily_flow":
            findings.append(
                SourceContractFinding(
                    severity="INFO",
                    code="TRACKED_BROKER_SUBSET",
                    table=table,
                    field=None,
                    message=(
                        "broker_daily_flow captures tracked broker codes only, not "
                        "full market broker composition."
                    ),
                    impact="Do not present this table as exhaustive broker composition.",
                )
            )

        return tuple(findings)


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
