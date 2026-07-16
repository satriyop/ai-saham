"""Tests for AuditSourceReconciliationUseCase (DQ-001B)."""

from __future__ import annotations

from src.application.use_case.audit_source_reconciliation_use_case import (
    AuditSourceReconciliationResponse,
    AuditSourceReconciliationUseCase,
    RawBrokerDailyFlowObservation,
    RawBrokerSummariesObservation,
    RawCandlesOhlcObservation,
    RawForeignFlowReconciliationObservation,
)


def _fixed_clock() -> str:
    return "2026-07-16T00:00:00+00:00"


class _FakeReader:
    def __init__(
        self,
        database_exists: bool = True,
        candles: RawCandlesOhlcObservation | None = None,
        broker_summaries: RawBrokerSummariesObservation | None = None,
        broker_daily_flow: RawBrokerDailyFlowObservation | None = None,
        foreign_flow: RawForeignFlowReconciliationObservation | None = None,
    ):
        self._database_exists = database_exists
        self._candles = candles or RawCandlesOhlcObservation(exists=True, row_count=10)
        self._broker_summaries = broker_summaries or RawBrokerSummariesObservation(
            exists=True, row_count=10
        )
        self._broker_daily_flow = broker_daily_flow or RawBrokerDailyFlowObservation(
            exists=True, row_count=10
        )
        self._foreign_flow = foreign_flow or RawForeignFlowReconciliationObservation(
            foreign_flow_points_exists=True,
            foreign_flow_points_schema_sufficient=True,
            matched_row_count=5,
            mismatch_count=0,
        )

    def database_exists(self) -> bool:
        return self._database_exists

    def observe_candles_ohlc(self) -> RawCandlesOhlcObservation:
        return self._candles

    def observe_broker_summaries(self) -> RawBrokerSummariesObservation:
        return self._broker_summaries

    def observe_broker_daily_flow(self) -> RawBrokerDailyFlowObservation:
        return self._broker_daily_flow

    def observe_foreign_flow_reconciliation(self) -> RawForeignFlowReconciliationObservation:
        return self._foreign_flow


def test_happy_path_aggregates_to_pass_with_expected_info_findings():
    reader = _FakeReader()
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert isinstance(response, AuditSourceReconciliationResponse)
    assert response.artifact_type == "source_reconciliation_audit"
    assert response.schema_version == 1
    assert response.generated_at == "2026-07-16T00:00:00+00:00"
    assert response.status == "PASS"
    assert len(response.checks) == 4
    info_codes = {f.code for f in response.findings if f.severity == "INFO"}
    assert "TRACKED_BROKER_SUBSET_NOT_FULL_MARKET" in info_codes
    fail_or_warn = [f for f in response.findings if f.severity in ("FAIL", "WARN")]
    assert fail_or_warn == []


def test_candles_ohlc_violation_produces_fail_status():
    reader = _FakeReader(
        candles=RawCandlesOhlcObservation(
            exists=True,
            row_count=10,
            invalid_ohlc_count=2,
            invalid_ohlc_samples=({"ticker": "BBCA", "date": "2026-01-02"},),
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    fail_findings = [f for f in response.findings if f.code == "INVALID_OHLC_INVARIANT"]
    assert len(fail_findings) == 1
    assert fail_findings[0].severity == "FAIL"
    assert fail_findings[0].mismatch_count == 2


def test_finding_sample_rows_are_preserved():
    sample = {"ticker": "BBCA", "date": "2026-01-02", "volume": -5}
    reader = _FakeReader(
        candles=RawCandlesOhlcObservation(
            exists=True,
            row_count=10,
            negative_volume_count=1,
            negative_volume_samples=(sample,),
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    finding = next(f for f in response.findings if f.code == "NEGATIVE_CANDLE_VOLUME")
    assert finding.sample_rows == (sample,)


def test_missing_table_causes_fail_without_crash():
    reader = _FakeReader(candles=RawCandlesOhlcObservation(exists=False))
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    candles_check = next(c for c in response.checks if c.name == "candles_ohlc_invariants")
    assert candles_check.status == "FAIL"
    assert any(f.code == "MISSING_TABLE" and f.table == "candles" for f in response.findings)


def test_database_missing_returns_fail_without_crashing():
    reader = _FakeReader(database_exists=False)
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    assert response.checks == ()
    assert any(f.code == "DATABASE_MISSING" for f in response.findings)


def test_broker_summary_duplicate_identity_fails():
    reader = _FakeReader(
        broker_summaries=RawBrokerSummariesObservation(
            exists=True, row_count=10, duplicate_identity_count=3
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "DUPLICATE_BROKER_SUMMARY_IDENTITY" for f in response.findings)


def test_tracked_broker_net_mismatch_fails():
    reader = _FakeReader(
        broker_daily_flow=RawBrokerDailyFlowObservation(
            exists=True, row_count=10, net_mismatch_count=4
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "TRACKED_BROKER_NET_MISMATCH" for f in response.findings)


def test_foreign_flow_unreconcilable_schema_warns_not_fails():
    reader = _FakeReader(
        foreign_flow=RawForeignFlowReconciliationObservation(
            foreign_flow_points_exists=True,
            foreign_flow_points_schema_sufficient=False,
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "WARN"
    assert any(
        f.code == "FOREIGN_FLOW_POINTS_UNRECONCILABLE_SCHEMA" and f.severity == "WARN"
        for f in response.findings
    )


def test_foreign_flow_mismatch_fails():
    reader = _FakeReader(
        foreign_flow=RawForeignFlowReconciliationObservation(
            foreign_flow_points_exists=True,
            foreign_flow_points_schema_sufficient=True,
            matched_row_count=5,
            mismatch_count=2,
        )
    )
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "FOREIGN_FLOW_RECONCILIATION_MISMATCH" for f in response.findings)


def test_response_to_dict_includes_required_root_keys():
    reader = _FakeReader()
    use_case = AuditSourceReconciliationUseCase(reader, clock=_fixed_clock)

    payload = use_case.execute().to_dict()

    for key in ("artifact_type", "schema_version", "generated_at", "status", "checks", "findings"):
        assert key in payload
    assert payload["artifact_type"] == "source_reconciliation_audit"
    assert payload["schema_version"] == 1
