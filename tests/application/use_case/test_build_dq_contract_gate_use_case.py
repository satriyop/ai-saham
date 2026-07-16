"""Tests for BuildDQContractGateUseCase — the DQ-CONTRACT-GATE aggregator."""

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


def test_gate_passes_when_both_audits_pass():
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
    assert response.artifact_type == "dq_contract_gate"
    assert response.schema_version == 1
    assert response.generated_at == "2026-07-16T00:00:00+00:00"
    assert contracts.call_count == 1
    assert reconciliation.call_count == 1


def test_gate_fails_when_source_contracts_fail():
    contracts = _FakeAuditRunner(
        _FakeAuditResponse(
            status="FAIL",
            findings=(
                _FakeFinding(
                    severity="FAIL",
                    code="MISSING_FIELD",
                    table="candles",
                    field="ticker",
                    message="candles.ticker does not exist.",
                ),
            ),
        )
    )
    reconciliation = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "FAIL"
    assert response.source_contract_status == "FAIL"
    assert response.source_reconciliation_status == "PASS"
    assert len(response.blockers) == 1
    blocker = response.blockers[0]
    assert blocker.source == "source_contracts"
    assert blocker.severity == "FAIL"
    assert blocker.code == "MISSING_FIELD"
    assert blocker.table == "candles"
    assert blocker.field == "ticker"


def test_gate_fails_when_reconciliation_fails():
    contracts = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))
    reconciliation = _FakeAuditRunner(
        _FakeAuditResponse(
            status="FAIL",
            findings=(
                _FakeFinding(
                    severity="FAIL",
                    code="INVALID_OHLC",
                    table="candles",
                    field=None,
                    message="high < low",
                ),
            ),
        )
    )

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "FAIL"
    assert response.source_contract_status == "PASS"
    assert response.source_reconciliation_status == "FAIL"
    assert len(response.blockers) == 1
    blocker = response.blockers[0]
    assert blocker.source == "source_reconciliation"
    assert blocker.code == "INVALID_OHLC"
    assert blocker.table == "candles"
    assert blocker.field is None


def test_warn_on_either_audit_is_treated_as_gate_failure():
    """Fail closed: a WARN status (not just FAIL) must not pass the gate."""
    contracts = _FakeAuditRunner(
        _FakeAuditResponse(
            status="WARN",
            findings=(
                _FakeFinding(
                    severity="WARN",
                    code="NULLS_IN_OPTIONAL_FIELD",
                    table="analyst_cache",
                    field="avg_price_target",
                    message="3 null value(s).",
                ),
            ),
        )
    )
    reconciliation = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "FAIL"
    assert response.source_contract_status == "WARN"
    assert len(response.blockers) == 1
    assert response.blockers[0].severity == "WARN"


def test_gate_fails_when_both_audits_fail_and_blockers_include_both_sources():
    contracts = _FakeAuditRunner(
        _FakeAuditResponse(
            status="FAIL",
            findings=(
                _FakeFinding(
                    severity="FAIL",
                    code="MISSING_TABLE",
                    table="stock_meta",
                    field=None,
                    message="stock_meta does not exist.",
                ),
            ),
        )
    )
    reconciliation = _FakeAuditRunner(
        _FakeAuditResponse(
            status="FAIL",
            findings=(
                _FakeFinding(
                    severity="FAIL",
                    code="ARITHMETIC_MISMATCH",
                    table="broker_daily_flow",
                    field="net_lot",
                    message="net_lot != buy_lot - sell_lot",
                ),
            ),
        )
    )

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "FAIL"
    sources = {b.source for b in response.blockers}
    assert sources == {"source_contracts", "source_reconciliation"}
    assert len(response.blockers) == 2


def test_info_findings_do_not_become_blockers():
    contracts = _FakeAuditRunner(
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
        )
    )
    reconciliation = _FakeAuditRunner(_FakeAuditResponse(status="PASS"))

    response = BuildDQContractGateUseCase(
        source_contracts_use_case=contracts,
        source_reconciliation_use_case=reconciliation,
        clock=_clock,
    ).execute()

    assert response.status == "PASS"
    assert response.blockers == ()
