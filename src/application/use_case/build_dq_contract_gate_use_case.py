"""
Read-only DQ-CONTRACT-GATE evaluator.

Combines the existing DQ-001A source-field contract audit and DQ-001B/D/E
source reconciliation audit into one machine-verifiable gate. Never repairs,
quarantines, or mutates data, and never re-derives contract/reconciliation
logic itself — it only runs the two existing read-only audit use cases and
aggregates their status/findings.

Gate status is fail-closed: PASS only when both audits report PASS. A WARN
on either audit is treated as a gate failure, not a pass — this gate is a
CI/automation trip-wire, not a human-readable report (those remain
`source-contracts`/`reconcile-sources`, unchanged by this gate).

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class DQContractGateBlocker:
    """One machine-readable reason the gate is not PASS."""

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
    blockers: tuple[DQContractGateBlocker, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "source_contract_status": self.source_contract_status,
            "source_reconciliation_status": self.source_reconciliation_status,
            "blockers": [b.to_dict() for b in self.blockers],
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


# Findings at these severities are exactly the ones that can move a sub-audit
# off PASS (see aggregate_status in both audits' DTOs, which only worsens
# status for FAIL/WARN and ignores INFO) — so filtering on this set surfaces
# every reason the gate isn't PASS, with no double logic to keep in sync.
_BLOCKING_SEVERITIES = ("FAIL", "WARN")


class BuildDQContractGateUseCase:
    """Evaluate the DQ-CONTRACT-GATE: PASS only if source-contracts and
    reconcile-sources both report PASS; WARN on either is a gate failure."""

    _ARTIFACT_TYPE = "dq_contract_gate"
    _SCHEMA_VERSION = 1

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

        blockers = [
            *_blockers_from(contracts_response, source="source_contracts"),
            *_blockers_from(reconciliation_response, source="source_reconciliation"),
        ]

        gate_status = (
            "PASS"
            if contracts_response.status == "PASS"
            and reconciliation_response.status == "PASS"
            else "FAIL"
        )

        return DQContractGateResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            status=gate_status,
            source_contract_status=contracts_response.status,
            source_reconciliation_status=reconciliation_response.status,
            blockers=tuple(blockers),
        )


def _blockers_from(
    response: _AuditResponseLike, *, source: str
) -> list[DQContractGateBlocker]:
    return [
        DQContractGateBlocker(
            source=source,
            severity=finding.severity,
            code=finding.code,
            table=finding.table or None,
            field=finding.field,
            message=finding.message,
        )
        for finding in response.findings
        if finding.severity in _BLOCKING_SEVERITIES
    ]


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
