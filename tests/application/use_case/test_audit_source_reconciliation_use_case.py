"""Tests for AuditSourceReconciliationUseCase (DQ-001B core, DQ-001D enrichment,
DQ-001E signal-artifact/market-context)."""

from __future__ import annotations

from src.application.dto.source_reconciliation_dto import (
    RawCandidateObservationIdentityObservation,
    RawCorporateActionLinkageObservation,
    RawInsiderCacheObservation,
    RawLearningObservationsRiskPitObservation,
    RawMarketContextSnapshotObservation,
    RawPitCacheObservation,
    RawRegimeObservationsObservation,
    RawSeasonalityObservation,
    RawSignalForwardLabelsLinkageObservation,
    RawStockMetaObservation,
    RawTickerNotationObservation,
)
from src.application.use_case.audit_source_reconciliation_use_case import (
    AuditSourceReconciliationResponse,
    AuditSourceReconciliationUseCase,
    RawBrokerDailyFlowObservation,
    RawBrokerSummariesObservation,
    RawCandlesOhlcObservation,
    RawForeignFlowReconciliationObservation,
)


class _EmptyArtifactReader:
    """DQ-001B/D-only tests don't exercise signal-artifact tables; this fake
    reports every artifact table as existing-but-empty so it contributes no
    findings and never changes overall PASS/FAIL/WARN status."""

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation:
        return RawCandidateObservationIdentityObservation(exists=True, row_count=0)

    def observe_signal_forward_labels_linkage(
        self,
    ) -> RawSignalForwardLabelsLinkageObservation:
        return RawSignalForwardLabelsLinkageObservation(
            exists=True, row_count=0, linkage_provable=True
        )

    def observe_market_context_snapshot_identity(
        self,
    ) -> RawMarketContextSnapshotObservation:
        return RawMarketContextSnapshotObservation(exists=True, row_count=0)

    def observe_regime_observations_identity(self) -> RawRegimeObservationsObservation:
        return RawRegimeObservationsObservation(exists=True, row_count=0)

    def observe_learning_observations_risk_pit(
        self,
    ) -> RawLearningObservationsRiskPitObservation:
        return RawLearningObservationsRiskPitObservation(exists=True, row_count=0)


class _EmptyEnrichmentReader:
    """DQ-001B-only tests don't exercise enrichment tables; this fake reports
    every enrichment table as existing-but-empty so it contributes only
    harmless INFO findings and never changes overall PASS/FAIL/WARN status."""

    def observe_seasonality(self) -> RawSeasonalityObservation:
        return RawSeasonalityObservation(exists=True, row_count=0)

    def observe_company_fundamentals(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_analyst_cache(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_insider_cache(self) -> RawInsiderCacheObservation:
        return RawInsiderCacheObservation(exists=True, row_count=0)

    def observe_corporate_action_linkage(self) -> RawCorporateActionLinkageObservation:
        return RawCorporateActionLinkageObservation(
            events_exists=True,
            event_dates_exists=True,
            events_row_count=0,
            event_dates_row_count=0,
        )

    def observe_forward_estimates(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_ticker_notation(self) -> RawTickerNotationObservation:
        return RawTickerNotationObservation(exists=True, row_count=0)

    def observe_stock_meta(self) -> RawStockMetaObservation:
        return RawStockMetaObservation(exists=True, row_count=0)


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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert isinstance(response, AuditSourceReconciliationResponse)
    assert response.artifact_type == "source_reconciliation_audit"
    assert response.schema_version == 1
    assert response.generated_at == "2026-07-16T00:00:00+00:00"
    assert response.status == "PASS"
    assert len(response.checks) == 17  # 4 core + 8 enrichment + 5 artifact (incl. learning PIT)
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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    finding = next(f for f in response.findings if f.code == "NEGATIVE_CANDLE_VOLUME")
    assert finding.sample_rows == (sample,)


def test_missing_table_causes_fail_without_crash():
    reader = _FakeReader(candles=RawCandlesOhlcObservation(exists=False))
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    candles_check = next(c for c in response.checks if c.name == "candles_ohlc_invariants")
    assert candles_check.status == "FAIL"
    assert any(f.code == "MISSING_TABLE" and f.table == "candles" for f in response.findings)


def test_database_missing_returns_fail_without_crashing():
    reader = _FakeReader(database_exists=False)
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "DUPLICATE_BROKER_SUMMARY_IDENTITY" for f in response.findings)


def test_tracked_broker_net_mismatch_fails():
    reader = _FakeReader(
        broker_daily_flow=RawBrokerDailyFlowObservation(
            exists=True, row_count=10, net_mismatch_count=4
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

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
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "FOREIGN_FLOW_RECONCILIATION_MISMATCH" for f in response.findings)


def test_response_to_dict_includes_required_root_keys():
    reader = _FakeReader()
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    payload = use_case.execute().to_dict()

    for key in ("artifact_type", "schema_version", "generated_at", "status", "checks", "findings"):
        assert key in payload


# ── DQ-001D: enrichment reconciliation findings ──────────────────────────


class _FakeEnrichmentReader:
    def __init__(
        self,
        seasonality: RawSeasonalityObservation | None = None,
        company_fundamentals: RawPitCacheObservation | None = None,
        analyst_cache: RawPitCacheObservation | None = None,
        insider_cache: RawInsiderCacheObservation | None = None,
        corporate_action_linkage: RawCorporateActionLinkageObservation | None = None,
        forward_estimates: RawPitCacheObservation | None = None,
        ticker_notation: RawTickerNotationObservation | None = None,
        stock_meta: RawStockMetaObservation | None = None,
    ):
        self._seasonality = seasonality or RawSeasonalityObservation(exists=True, row_count=0)
        self._company_fundamentals = company_fundamentals or RawPitCacheObservation(
            exists=True, row_count=0
        )
        self._analyst_cache = analyst_cache or RawPitCacheObservation(exists=True, row_count=0)
        self._insider_cache = insider_cache or RawInsiderCacheObservation(exists=True, row_count=0)
        self._corporate_action_linkage = corporate_action_linkage or (
            RawCorporateActionLinkageObservation(
                events_exists=True,
                event_dates_exists=True,
                events_row_count=0,
                event_dates_row_count=0,
            )
        )
        self._forward_estimates = forward_estimates or RawPitCacheObservation(
            exists=True, row_count=0
        )
        self._ticker_notation = ticker_notation or RawTickerNotationObservation(
            exists=True, row_count=0
        )
        self._stock_meta = stock_meta or RawStockMetaObservation(exists=True, row_count=0)

    def observe_seasonality(self) -> RawSeasonalityObservation:
        return self._seasonality

    def observe_company_fundamentals(self) -> RawPitCacheObservation:
        return self._company_fundamentals

    def observe_analyst_cache(self) -> RawPitCacheObservation:
        return self._analyst_cache

    def observe_insider_cache(self) -> RawInsiderCacheObservation:
        return self._insider_cache

    def observe_corporate_action_linkage(self) -> RawCorporateActionLinkageObservation:
        return self._corporate_action_linkage

    def observe_forward_estimates(self) -> RawPitCacheObservation:
        return self._forward_estimates

    def observe_ticker_notation(self) -> RawTickerNotationObservation:
        return self._ticker_notation

    def observe_stock_meta(self) -> RawStockMetaObservation:
        return self._stock_meta


def test_enrichment_findings_are_included_in_response():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        seasonality=RawSeasonalityObservation(
            exists=True,
            row_count=5,
            invalid_source_count=2,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert any(f.code == "SEASONALITY_INVALID_SOURCE" for f in response.findings)
    seasonality_check = next(
        c for c in response.checks if c.name == "seasonality_provenance_consistency"
    )
    assert seasonality_check.status == "FAIL"


def test_overall_status_fails_when_any_enrichment_check_fails():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        seasonality=RawSeasonalityObservation(
            exists=True,
            row_count=5,
            null_fetched_at_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"


def test_warn_only_enrichment_findings_produce_warn_not_fail():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        company_fundamentals=RawPitCacheObservation(
            exists=True,
            row_count=5,
            duplicate_identity_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "WARN"
    fail_findings = [f for f in response.findings if f.severity == "FAIL"]
    assert fail_findings == []


def test_insider_missing_identity_fails():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        insider_cache=RawInsiderCacheObservation(
            exists=True,
            row_count=3,
            missing_identity_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "INSIDER_MISSING_IDENTITY" for f in response.findings)


def test_seasonality_schema_insufficient_produces_fail_not_crash():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        seasonality=RawSeasonalityObservation(
            exists=True,
            row_count=1,
            schema_sufficient=False,
            missing_columns=("source", "fetched_at"),
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(
        f.code == "SEASONALITY_SCHEMA_INSUFFICIENT" and f.severity == "FAIL"
        for f in response.findings
    )


def test_corporate_action_date_orphan_fails():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader(
        corporate_action_linkage=RawCorporateActionLinkageObservation(
            events_exists=True,
            event_dates_exists=True,
            events_row_count=2,
            event_dates_row_count=3,
            orphan_date_rows_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "CORPORATE_ACTION_DATE_ORPHAN" for f in response.findings)


def test_ticker_notation_always_emits_current_cache_info():
    reader = _FakeReader()
    enrichment_reader = _FakeEnrichmentReader()
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=enrichment_reader,
        artifact_reader=_EmptyArtifactReader(),
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert any(
        f.code == "TICKER_NOTATION_CURRENT_CACHE_LIMITATION" and f.severity == "INFO"
        for f in response.findings
    )


# ── DQ-001E: signal-artifact / market-context reconciliation findings ────


class _FakeArtifactReader:
    def __init__(
        self,
        candidate_observations: RawCandidateObservationIdentityObservation | None = None,
        signal_forward_labels: RawSignalForwardLabelsLinkageObservation | None = None,
        market_context_snapshot: RawMarketContextSnapshotObservation | None = None,
        regime_observations: RawRegimeObservationsObservation | None = None,
        learning_observations_risk_pit: RawLearningObservationsRiskPitObservation | None = None,
    ):
        self._candidate_observations = candidate_observations or (
            RawCandidateObservationIdentityObservation(exists=True, row_count=0)
        )
        self._signal_forward_labels = signal_forward_labels or (
            RawSignalForwardLabelsLinkageObservation(
                exists=True, row_count=0, linkage_provable=True
            )
        )
        self._market_context_snapshot = market_context_snapshot or (
            RawMarketContextSnapshotObservation(exists=True, row_count=0)
        )
        self._regime_observations = regime_observations or (
            RawRegimeObservationsObservation(exists=True, row_count=0)
        )
        self._learning_observations_risk_pit = learning_observations_risk_pit or (
            RawLearningObservationsRiskPitObservation(exists=True, row_count=0)
        )

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation:
        return self._candidate_observations

    def observe_signal_forward_labels_linkage(
        self,
    ) -> RawSignalForwardLabelsLinkageObservation:
        return self._signal_forward_labels

    def observe_market_context_snapshot_identity(
        self,
    ) -> RawMarketContextSnapshotObservation:
        return self._market_context_snapshot

    def observe_regime_observations_identity(self) -> RawRegimeObservationsObservation:
        return self._regime_observations

    def observe_learning_observations_risk_pit(
        self,
    ) -> RawLearningObservationsRiskPitObservation:
        return self._learning_observations_risk_pit


def test_artifact_findings_are_included_in_response():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader(
        candidate_observations=RawCandidateObservationIdentityObservation(
            exists=True,
            row_count=5,
            invalid_payload_json_count=2,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert any(
        f.code == "LEARNING_OBSERVATIONS_INVALID_DECISION_PAYLOAD_JSON" for f in response.findings
    )
    check = next(c for c in response.checks if c.name == "learning_observations_identity")
    assert check.status == "FAIL"


def test_any_artifact_fail_produces_overall_fail():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader(
        signal_forward_labels=RawSignalForwardLabelsLinkageObservation(
            exists=True,
            row_count=5,
            linkage_provable=True,
            orphan_linkage_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"


def test_artifact_warn_only_findings_produce_warn_not_fail():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader(
        candidate_observations=RawCandidateObservationIdentityObservation(
            exists=True,
            row_count=5,
            legacy_row_count=5,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "WARN"
    fail_findings = [f for f in response.findings if f.severity == "FAIL"]
    assert fail_findings == []


def test_existing_core_and_enrichment_checks_still_included_with_artifact_reader():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader()
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    check_names = {c.name for c in response.checks}
    for expected in (
        "candles_ohlc_invariants",
        "broker_summaries_arithmetic_identity",
        "broker_daily_flow_arithmetic_scope",
        "foreign_flow_reconciliation",
        "seasonality_provenance_consistency",
        "learning_observations_identity",
        "learning_outcome_labels_identity_linkage",
        "market_context_snapshot_identity",
        "regime_observations_identity",
        "learning_observations_risk_pit",
    ):
        assert expected in check_names


def test_signal_forward_labels_linkage_unprovable_warns():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader(
        signal_forward_labels=RawSignalForwardLabelsLinkageObservation(
            exists=True,
            row_count=3,
            linkage_provable=False,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert any(
        f.code == "LEARNING_OUTCOME_LABELS_LINKAGE_UNPROVABLE" and f.severity == "WARN"
        for f in response.findings
    )
    assert response.status == "WARN"


def test_regime_observations_invalid_regime_fails():
    reader = _FakeReader()
    artifact_reader = _FakeArtifactReader(
        regime_observations=RawRegimeObservationsObservation(
            exists=True,
            row_count=2,
            invalid_regime_count=1,
        )
    )
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=artifact_reader,
        clock=_fixed_clock,
    )

    response = use_case.execute()

    assert response.status == "FAIL"
    assert any(f.code == "REGIME_OBSERVATIONS_INVALID_REGIME" for f in response.findings)
