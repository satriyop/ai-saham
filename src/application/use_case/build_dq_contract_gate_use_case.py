"""
Read-only DQ-CONTRACT-GATE evaluator.

Combines the existing DQ-001A source-field contract audit and DQ-001B/D/E
source reconciliation audit into one machine-verifiable gate. Never repairs,
quarantines, or mutates data, and never re-derives contract/reconciliation
logic itself — it only runs the two existing read-only audit use cases and
aggregates their status/findings.

Gate status is fail-closed but severity-honest: it FAILs only on FAIL findings
or a failing/invalid sub-audit status. WARN findings remain fully visible but
are non-blocking — optional-data warnings must not trip the CI gate. Severity
ownership stays in the underlying audits: a finding that must block has to be
emitted there as FAIL. The gate never downgrades, hides, or re-classifies a
source finding.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

_VALID_SUB_AUDIT_STATUSES = ("PASS", "WARN", "FAIL")


@dataclass(frozen=True)
class DQContractGateFinding:
    """One machine-readable gate finding, carrying its source severity verbatim."""

    source: str  # "source_contracts" | "source_reconciliation"
    severity: str  # "FAIL" | "WARN"
    code: str
    table: str | None
    field: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "severity": self.severity,
            "code": self.code,
            "table": self.table,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class DQContractGateResponse:
    artifact_type: str
    schema_version: int
    generated_at: str
    status: str  # "PASS" | "FAIL"
    source_contract_status: str
    source_reconciliation_status: str
    blockers: tuple[DQContractGateFinding, ...]  # severity FAIL only
    warnings: tuple[DQContractGateFinding, ...]  # severity WARN only

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "source_contract_status": self.source_contract_status,
            "source_reconciliation_status": self.source_reconciliation_status,
            "blockers": [b.to_dict() for b in self.blockers],
            "warnings": [w.to_dict() for w in self.warnings],
        }


class _FindingLike(Protocol):
    severity: str
    code: str
    table: str
    field: str | None
    message: str


class _AuditResponseLike(Protocol):
    status: str
    findings: tuple[_FindingLike, ...]


class SourceContractsAuditRunner(Protocol):
    def execute(self) -> _AuditResponseLike: ...


class SourceReconciliationAuditRunner(Protocol):
    def execute(self) -> _AuditResponseLike: ...


class BuildDQContractGateUseCase:
    """Evaluate the DQ-CONTRACT-GATE: FAIL only when a FAIL finding exists or a
    sub-audit reports a failing/invalid status; WARN findings are visible but
    non-blocking."""

    _ARTIFACT_TYPE = "dq_contract_gate"
    # v1 -> v2: blocker semantics changed (WARN is no longer a blocker) and the
    # serialized artifact now carries a separate `warnings` array.
    _SCHEMA_VERSION = 2

    def __init__(
        self,
        source_contracts_use_case: SourceContractsAuditRunner,
        source_reconciliation_use_case: SourceReconciliationAuditRunner,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._source_contracts = source_contracts_use_case
        self._source_reconciliation = source_reconciliation_use_case
        self._clock = clock or _default_clock

    def execute(self) -> DQContractGateResponse:
        contracts_response = self._source_contracts.execute()
        reconciliation_response = self._source_reconciliation.execute()

        findings = [
            *_findings_from(contracts_response, source="source_contracts"),
            *_findings_from(reconciliation_response, source="source_reconciliation"),
        ]

        blockers = [f for f in findings if f.severity == "FAIL"]
        warnings = [f for f in findings if f.severity == "WARN"]

        # Fail closed on inconsistent/invalid sub-audit status: never infer PASS
        # from findings alone. A FAIL status with no FAIL finding, or a status
        # outside PASS|WARN|FAIL, becomes a synthetic blocker.
        blockers.extend(
            _status_consistency_blockers(
                contracts_response.status,
                source="source_contracts",
                has_fail_finding=any(
                    f.source == "source_contracts" for f in blockers
                ),
            )
        )
        blockers.extend(
            _status_consistency_blockers(
                reconciliation_response.status,
                source="source_reconciliation",
                has_fail_finding=any(
                    f.source == "source_reconciliation" for f in blockers
                ),
            )
        )

        gate_status = "FAIL" if blockers else "PASS"

        return DQContractGateResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            status=gate_status,
            source_contract_status=contracts_response.status,
            source_reconciliation_status=reconciliation_response.status,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )


def _findings_from(
    response: _AuditResponseLike, *, source: str
) -> list[DQContractGateFinding]:
    """Convert sub-audit findings verbatim, preserving severity. Partitioning
    into blockers/warnings happens in the caller — severity is never mutated
    and no code-based allowlist is applied here."""
    return [
        DQContractGateFinding(
            source=source,
            severity=finding.severity,
            code=finding.code,
            table=finding.table or None,
            field=finding.field,
            message=finding.message,
        )
        for finding in response.findings
    ]


def _status_consistency_blockers(
    status: str, *, source: str, has_fail_finding: bool
) -> list[DQContractGateFinding]:
    if status not in _VALID_SUB_AUDIT_STATUSES:
        return [
            DQContractGateFinding(
                source=source,
                severity="FAIL",
                code="INVALID_AUDIT_STATUS",
                table=None,
                field=None,
                message=(
                    f"{source} returned status {status!r} outside "
                    f"{_VALID_SUB_AUDIT_STATUSES}; failing closed."
                ),
            )
        ]
    if status == "FAIL" and not has_fail_finding:
        return [
            DQContractGateFinding(
                source=source,
                severity="FAIL",
                code="AUDIT_STATUS_FAIL_WITHOUT_BLOCKING_FINDING",
                table=None,
                field=None,
                message=(
                    f"{source} reported status FAIL but supplied no FAIL "
                    "finding; failing closed."
                ),
            )
        ]
    return []


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
