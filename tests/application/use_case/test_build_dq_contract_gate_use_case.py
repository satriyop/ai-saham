"""Tests for BuildDQContractGateUseCase — the DQ-CONTRACT-GATE aggregator.

Contract: FAIL findings (or a failing/invalid sub-audit status) block; WARN
findings remain visible but never block. INFO is neither.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.use_case.build_dq_contract_gate_use_case import (
    BuildDQContractGateUseCase,
)


@dataclass(frozen=True)
class _FakeFinding:
    severity: str
    code: str
    table: str
    field: str | None
    message: str
    impact: str = "n/a"


@dataclass(frozen=True)
class _FakeAuditResponse:
    status: str
    findings: tuple[_FakeFinding, ...] = field(default_factory=tuple)


class _FakeAuditRunner:
    def __init__(self, response: _FakeAuditResponse) -> None:
        self._response = response
        self.call_count = 0

    def execute(self) -> _FakeAuditResponse:
        self.call_count += 1
        return self._response


def _clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def _gate(contracts: _FakeAuditResponse, reconciliation: _FakeAuditResponse):
    return BuildDQContractGateUseCase(
        source_contracts_use_case=_FakeAuditRunner(contracts),
        source_reconciliation_use_case=_FakeAuditRunner(reconciliation),
        clock=_clock,
    ).execute()


def _warn(code: str, table: str = "analyst_cache") -> _FakeFinding:
    return _FakeFinding(
        severity="WARN",
        code=code,
        table=table,
        field="avg_price_target",
        message=f"{code}: non-blocking optional-data warning.",
    )


def _fail(code: str, table: str = "candles") -> _FakeFinding:
    return _FakeFinding(
        severity="FAIL",
        code=code,
        table=table,
        field="ticker",
        message=f"{code}: blocking contract violation.",
    )


# 1. PASS + PASS, no findings.
def test_gate_passes_when_both_audits_pass_with_no_findings():
    contracts = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))
    reconciliation = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "PASS"
    assert response.source_contract_status == "PASS"
    assert response.source_reconciliation_status == "PASS"
    assert response.blockers == ()
    assert response.warnings == ()
    assert response.artifact_type == "dq_contract_gate"
    assert response.schema_version == 2
    assert response.generated_at == "2026-07-16T00:00:00+00:00"
    assert contracts.call_count == 1
    assert reconciliation.call_count == 1


# 2. WARN + PASS with one warning.
def test_gate_passes_with_warn_sub_audit_and_retains_warning():
    response = _gate(
        _FakeAuditResponse(status="WARN", findings=(_warn("NULLS_IN_OPTIONAL_FIELD"),)),
        _FakeAuditResponse(status="PASS"),
    )

    assert response.status == "PASS"
    assert response.source_contract_status == "WARN"
    assert response.blockers == ()
    assert len(response.warnings) == 1
    assert response.warnings[0].severity == "WARN"
    assert response.warnings[0].code == "NULLS_IN_OPTIONAL_FIELD"
    assert response.warnings[0].source == "source_contracts"


# 3. WARN + WARN, warnings retained from both sources.
def test_gate_passes_when_both_sub_audits_warn_and_keeps_all_warnings():
    response = _gate(
        _FakeAuditResponse(status="WARN", findings=(_warn("W_CONTRACTS"),)),
        _FakeAuditResponse(status="WARN", findings=(_warn("W_RECON", table="broker_daily_flow"),)),
    )

    assert response.status == "PASS"
    assert response.source_contract_status == "WARN"
    assert response.source_reconciliation_status == "WARN"
    assert response.blockers == ()
    assert {w.source for w in response.warnings} == {
        "source_contracts",
        "source_reconciliation",
    }
    assert {w.code for w in response.warnings} == {"W_CONTRACTS", "W_RECON"}


# 4. One FAIL finding.
def test_gate_fails_on_a_single_fail_finding():
    response = _gate(
        _FakeAuditResponse(status="FAIL", findings=(_fail("MISSING_FIELD"),)),
        _FakeAuditResponse(status="PASS"),
    )

    assert response.status == "FAIL"
    assert response.source_contract_status == "FAIL"
    assert len(response.blockers) == 1
    assert response.blockers[0].severity == "FAIL"
    assert response.blockers[0].code == "MISSING_FIELD"
    assert response.blockers[0].source == "source_contracts"
    assert response.warnings == ()


# 5. Mixed FAIL and WARN across both sources.
def test_mixed_fail_and_warn_partition_into_blockers_and_warnings():
    response = _gate(
        _FakeAuditResponse(
            status="FAIL",
            findings=(_fail("MISSING_TABLE", table="stock_meta"), _warn("W_CONTRACTS")),
        ),
        _FakeAuditResponse(
            status="WARN", findings=(_warn("W_RECON", table="foreign_flow_points"),)
        ),
    )

    assert response.status == "FAIL"
    assert [b.severity for b in response.blockers] == ["FAIL"]
    assert response.blockers[0].code == "MISSING_TABLE"
    assert all(w.severity == "WARN" for w in response.warnings)
    assert {w.code for w in response.warnings} == {"W_CONTRACTS", "W_RECON"}
    # A FAIL never leaks into warnings and a WARN never leaks into blockers.
    assert all(b.severity != "WARN" for b in response.blockers)
    assert all(w.severity != "FAIL" for w in response.warnings)


# 6. Sub-audit status FAIL without a FAIL finding -> synthetic blocker.
def test_fail_status_without_fail_finding_creates_synthetic_blocker():
    response = _gate(
        _FakeAuditResponse(status="FAIL", findings=()),
        _FakeAuditResponse(status="PASS"),
    )

    assert response.status == "FAIL"
    assert len(response.blockers) == 1
    blocker = response.blockers[0]
    assert blocker.code == "AUDIT_STATUS_FAIL_WITHOUT_BLOCKING_FINDING"
    assert blocker.severity == "FAIL"
    assert blocker.source == "source_contracts"
    assert response.warnings == ()


def test_fail_status_with_fail_finding_does_not_add_synthetic_blocker():
    response = _gate(
        _FakeAuditResponse(status="FAIL", findings=(_fail("MISSING_FIELD"),)),
        _FakeAuditResponse(status="PASS"),
    )

    assert [b.code for b in response.blockers] == ["MISSING_FIELD"]


# 7. Unknown sub-audit status.
def test_unknown_sub_audit_status_fails_closed_with_invalid_status_blocker():
    response = _gate(
        _FakeAuditResponse(status="PASS"),
        _FakeAuditResponse(status="MYSTERY"),
    )

    assert response.status == "FAIL"
    codes = {b.code for b in response.blockers}
    assert "INVALID_AUDIT_STATUS" in codes
    invalid = next(b for b in response.blockers if b.code == "INVALID_AUDIT_STATUS")
    assert invalid.severity == "FAIL"
    assert invalid.source == "source_reconciliation"


# 8. INFO findings are neither blockers nor warnings.
def test_info_findings_are_neither_blockers_nor_warnings():
    response = _gate(
        _FakeAuditResponse(
            status="PASS",
            findings=(
                _FakeFinding(
                    severity="INFO",
                    code="TRACKED_BROKER_SUBSET",
                    table="broker_daily_flow",
                    field=None,
                    message="informational only",
                ),
            ),
        ),
        _FakeAuditResponse(status="PASS"),
    )

    assert response.status == "PASS"
    assert response.blockers == ()
    assert response.warnings == ()


# 9. Serialized JSON artifact.
def test_to_dict_emits_schema_version_2_with_blockers_and_warnings():
    response = _gate(
        _FakeAuditResponse(status="FAIL", findings=(_fail("MISSING_FIELD"), _warn("W_CONTRACTS"))),
        _FakeAuditResponse(status="WARN", findings=(_warn("W_RECON"),)),
    )

    payload = response.to_dict()
    assert payload["schema_version"] == 2
    assert isinstance(payload["blockers"], list)
    assert isinstance(payload["warnings"], list)
    assert [b["severity"] for b in payload["blockers"]] == ["FAIL"]
    assert {w["code"] for w in payload["warnings"]} == {"W_CONTRACTS", "W_RECON"}
    assert payload["status"] == "FAIL"
    assert payload["source_contract_status"] == "FAIL"
    assert payload["source_reconciliation_status"] == "WARN"
