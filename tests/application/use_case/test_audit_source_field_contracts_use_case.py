"""Tests for AuditSourceFieldContractsUseCase (DQ-001A)."""

from __future__ import annotations

from src.application.use_case.audit_source_field_contracts_use_case import (
    AuditSourceFieldContractsResponse,
    AuditSourceFieldContractsUseCase,
    RawFieldObservation,
    RawTableObservation,
    SourceFieldContract,
)

_TICKER_CONTRACT = SourceFieldContract(
    field="ticker",
    required=True,
    semantic_name="IDX ticker symbol",
    source_owner="candle provider",
    unit="text",
    sign_convention=None,
    aggregation="none",
    grain="one row per ticker/session",
    temporal_meaning="market session date",
    null_semantics="unavailable if null",
    point_in_time_support="HISTORICAL",
    null_policy="fail",
)

_SOURCE_CONTRACT = SourceFieldContract(
    field="source",
    required=True,
    semantic_name="Provider id",
    source_owner="candle provider",
    unit="provider id",
    sign_convention=None,
    aggregation="none",
    grain="one row per ticker/session",
    temporal_meaning="none",
    null_semantics="unknown source is invalid",
    point_in_time_support="HISTORICAL",
    null_policy="ignore",
    invalid_values=frozenset({"unknown"}),
    invalid_value_policy="fail",
)

_METRIC_CONTRACT = SourceFieldContract(
    field="foreign_buy_value",
    required=True,
    semantic_name="Foreign buy value",
    source_owner="broker provider",
    unit="IDR",
    sign_convention="non-negative",
    aggregation="daily",
    grain="one row per ticker/date/source",
    temporal_meaning="session value",
    null_semantics="unavailable if null",
    point_in_time_support="HISTORICAL",
    null_policy="warn",
)


class _FakeCatalog:
    def __init__(self, tables_and_contracts: dict[str, tuple[SourceFieldContract, ...]]):
        self._tables_and_contracts = tables_and_contracts

    def tables(self) -> tuple[str, ...]:
        return tuple(self._tables_and_contracts.keys())

    def contracts_for_table(self, table: str) -> tuple[SourceFieldContract, ...]:
        return self._tables_and_contracts.get(table, ())


class _FakeReader:
    def __init__(self, observations: dict[str, RawTableObservation], database_exists: bool = True):
        self._observations = observations
        self._database_exists = database_exists

    def database_exists(self) -> bool:
        return self._database_exists

    def observe_table(self, table: str) -> RawTableObservation:
        return self._observations.get(table, RawTableObservation(table=table, exists=False))


def _fixed_clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def test_execute_produces_complete_response_shape():
    catalog = _FakeCatalog({"candles": (_TICKER_CONTRACT, _SOURCE_CONTRACT)})
    reader = _FakeReader(
        {
            "candles": RawTableObservation(
                table="candles",
                exists=True,
                row_count=10,
                fields=(
                    RawFieldObservation(
                        field="ticker", exists=True, null_count=0, distinct_count=2
                    ),
                    RawFieldObservation(
                        field="source", exists=True, null_count=0, invalid_value_count=0
                    ),
                ),
            )
        }
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert isinstance(response, AuditSourceFieldContractsResponse)
    assert response.artifact_type == "source_field_contract_audit"
    assert response.schema_version == 1
    assert response.generated_at == "2026-07-16T00:00:00+00:00"
    assert len(response.tables) == 1
    assert response.tables[0].table == "candles"
    assert response.tables[0].contract_status == "PASS"
    assert response.status == "PASS"


def test_missing_required_field_makes_status_fail():
    catalog = _FakeCatalog({"candles": (_TICKER_CONTRACT,)})
    reader = _FakeReader(
        {"candles": RawTableObservation(table="candles", exists=True, row_count=5, fields=())}
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "FAIL"
    assert response.tables[0].contract_status == "FAIL"
    field_result = response.tables[0].fields[0]
    assert field_result.exists is False
    assert field_result.status == "FAIL"
    fail_findings = [f for f in response.findings if f.severity == "FAIL"]
    assert any(f.code == "MISSING_FIELD" for f in fail_findings)


def test_missing_table_produces_fail_status_and_finding():
    catalog = _FakeCatalog({"candles": (_TICKER_CONTRACT,)})
    reader = _FakeReader({})  # candles not present -> exists=False by default

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "FAIL"
    assert response.tables[0].exists is False
    assert any(f.code == "MISSING_TABLE" for f in response.findings)


def test_database_missing_returns_fail_without_crashing():
    catalog = _FakeCatalog({"candles": (_TICKER_CONTRACT,)})
    reader = _FakeReader({}, database_exists=False)

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "FAIL"
    assert response.tables == ()
    assert any(f.code == "DATABASE_MISSING" for f in response.findings)


def test_legacy_candidate_rows_produce_warning_not_crash():
    catalog = _FakeCatalog({"candidate_observations": ()})
    reader = _FakeReader(
        {
            "candidate_observations": RawTableObservation(
                table="candidate_observations",
                exists=True,
                row_count=100,
                fields=(),
                special_checks={"legacy_config_hash_count": 40},
            )
        }
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "WARN"
    legacy_findings = [f for f in response.findings if f.code == "LEGACY_NON_CANONICAL_IDENTITY"]
    assert len(legacy_findings) == 1
    assert legacy_findings[0].severity == "WARN"
    assert legacy_findings[0].table == "candidate_observations"


def test_invalid_source_value_fails_field_and_table():
    catalog = _FakeCatalog({"candles": (_SOURCE_CONTRACT,)})
    reader = _FakeReader(
        {
            "candles": RawTableObservation(
                table="candles",
                exists=True,
                row_count=3,
                fields=(
                    RawFieldObservation(
                        field="source", exists=True, null_count=0, invalid_value_count=1
                    ),
                ),
            )
        }
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "FAIL"
    field_result = response.tables[0].fields[0]
    assert field_result.status == "FAIL"
    assert any(f.code == "INVALID_FIELD_VALUE" for f in response.findings)


def test_null_in_optional_metric_field_warns_not_fails():
    catalog = _FakeCatalog({"broker_summaries": (_METRIC_CONTRACT,)})
    reader = _FakeReader(
        {
            "broker_summaries": RawTableObservation(
                table="broker_summaries",
                exists=True,
                row_count=10,
                fields=(RawFieldObservation(field="foreign_buy_value", exists=True, null_count=2),),
            )
        }
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    response = use_case.execute()

    assert response.status == "WARN"
    assert response.tables[0].fields[0].status == "WARN"


def test_response_to_dict_includes_required_root_keys():
    catalog = _FakeCatalog({"candles": (_TICKER_CONTRACT,)})
    reader = _FakeReader(
        {
            "candles": RawTableObservation(
                table="candles",
                exists=True,
                row_count=1,
                fields=(RawFieldObservation(field="ticker", exists=True, null_count=0),),
            )
        }
    )

    use_case = AuditSourceFieldContractsUseCase(reader, catalog, clock=_fixed_clock)
    payload = use_case.execute().to_dict()

    for key in ("artifact_type", "schema_version", "generated_at", "tables", "findings", "status"):
        assert key in payload
    assert payload["artifact_type"] == "source_field_contract_audit"
    assert payload["schema_version"] == 1
