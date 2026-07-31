"""
Read-only executable source reconciliation audit (DQ-001B core tables,
DQ-001D enrichment/source-context tables, DQ-001E signal-artifact and
market-context tables).

Proves OHLC/arithmetic invariants, identity uniqueness, payload
parseability, and cross-table overlaps/linkage for core market/broker
tables, enrichment/source-context tables, and canonical signal-artifact/
market-context tables. Never repairs, quarantines, or mutates data —
read-only findings only.

This module is an orchestrator only: it calls injected readers, delegates
per-table evaluation policy to source_reconciliation_core_evaluator,
source_reconciliation_enrichment_evaluator, and
source_reconciliation_artifact_evaluator, and assembles the response.
DTOs live in src/application/dto/source_reconciliation_dto.py and are
re-exported here for backward compatibility with existing import sites.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from typing import Callable, Protocol

from src.application.dto.source_reconciliation_dto import (
    AuditSourceReconciliationResponse,
    RawBrokerDailyFlowObservation,
    RawBrokerSummariesObservation,
    RawCandidateObservationIdentityObservation,
    RawCandlesOhlcObservation,
    RawCorporateActionLinkageObservation,
    RawForeignFlowReconciliationObservation,
    RawInsiderCacheObservation,
    RawLearningObservationsRiskPitObservation,
    RawMarketContextSnapshotObservation,
    RawPitCacheObservation,
    RawRegimeObservationsObservation,
    RawSeasonalityObservation,
    RawSignalForwardLabelsLinkageObservation,
    RawStockMetaObservation,
    RawTickerNotationObservation,
    SourceReconciliationCheckResult,
    SourceReconciliationFinding,
    aggregate_status,
)
from src.application.services import source_reconciliation_artifact_evaluator as artifact_eval
from src.application.services import source_reconciliation_core_evaluator as core_eval
from src.application.services import source_reconciliation_enrichment_evaluator as enrichment_eval

__all__ = [
    "ArtifactReconciliationReader",
    "AuditSourceReconciliationResponse",
    "AuditSourceReconciliationUseCase",
    "EnrichmentReconciliationReader",
    "RawBrokerDailyFlowObservation",
    "RawBrokerSummariesObservation",
    "RawCandidateObservationIdentityObservation",
    "RawCandlesOhlcObservation",
    "RawCorporateActionLinkageObservation",
    "RawForeignFlowReconciliationObservation",
    "RawInsiderCacheObservation",
    "RawLearningObservationsRiskPitObservation",
    "RawMarketContextSnapshotObservation",
    "RawPitCacheObservation",
    "RawRegimeObservationsObservation",
    "RawSeasonalityObservation",
    "RawSignalForwardLabelsLinkageObservation",
    "RawStockMetaObservation",
    "RawTickerNotationObservation",
    "SourceReconciliationCheckResult",
    "SourceReconciliationFinding",
    "SourceReconciliationReader",
]


class SourceReconciliationReader(Protocol):
    """Read-only observer of core market/broker reconciliation facts (DQ-001B)."""

    def database_exists(self) -> bool: ...

    def observe_candles_ohlc(self) -> RawCandlesOhlcObservation: ...

    def observe_broker_summaries(self) -> RawBrokerSummariesObservation: ...

    def observe_broker_daily_flow(self) -> RawBrokerDailyFlowObservation: ...

    def observe_foreign_flow_reconciliation(self) -> RawForeignFlowReconciliationObservation: ...


class EnrichmentReconciliationReader(Protocol):
    """Read-only observer of enrichment/source-context reconciliation facts (DQ-001D)."""

    def observe_seasonality(self) -> RawSeasonalityObservation: ...

    def observe_company_fundamentals(self) -> RawPitCacheObservation: ...

    def observe_analyst_cache(self) -> RawPitCacheObservation: ...

    def observe_insider_cache(self) -> RawInsiderCacheObservation: ...

    def observe_corporate_action_linkage(self) -> RawCorporateActionLinkageObservation: ...

    def observe_forward_estimates(self) -> RawPitCacheObservation: ...

    def observe_ticker_notation(self) -> RawTickerNotationObservation: ...

    def observe_stock_meta(self) -> RawStockMetaObservation: ...


class ArtifactReconciliationReader(Protocol):
    """Read-only observer of signal-artifact/market-context reconciliation facts (DQ-001E)."""

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation: ...

    def observe_signal_forward_labels_linkage(
        self,
    ) -> RawSignalForwardLabelsLinkageObservation: ...

    def observe_market_context_snapshot_identity(
        self,
    ) -> RawMarketContextSnapshotObservation: ...

    def observe_regime_observations_identity(self) -> RawRegimeObservationsObservation: ...

    def observe_learning_observations_risk_pit(
        self,
    ) -> RawLearningObservationsRiskPitObservation: ...


class AuditSourceReconciliationUseCase:
    """Evaluate executable source reconciliation checks (DQ-001B core, DQ-001D
    enrichment, DQ-001E signal-artifact/market-context)."""

    _ARTIFACT_TYPE = "source_reconciliation_audit"
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        reader: SourceReconciliationReader,
        enrichment_reader: EnrichmentReconciliationReader,
        artifact_reader: ArtifactReconciliationReader,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._reader = reader
        self._enrichment_reader = enrichment_reader
        self._artifact_reader = artifact_reader
        self._clock = clock or _default_clock

    def execute(self) -> AuditSourceReconciliationResponse:
        if not self._reader.database_exists():
            finding = SourceReconciliationFinding(
                severity="FAIL",
                code="DATABASE_MISSING",
                table="",
                field=None,
                message="SQLite database does not exist.",
                impact="No source reconciliation can be performed.",
            )
            return AuditSourceReconciliationResponse(
                artifact_type=self._ARTIFACT_TYPE,
                schema_version=self._SCHEMA_VERSION,
                generated_at=self._clock(),
                status="FAIL",
                checks=(),
                findings=(finding,),
            )

        checks: list[SourceReconciliationCheckResult] = []
        findings: list[SourceReconciliationFinding] = []

        for check, check_findings in (
            core_eval.evaluate_candles_ohlc(self._reader.observe_candles_ohlc()),
            core_eval.evaluate_broker_summaries(self._reader.observe_broker_summaries()),
            core_eval.evaluate_broker_daily_flow(self._reader.observe_broker_daily_flow()),
            core_eval.evaluate_foreign_flow_reconciliation(
                self._reader.observe_foreign_flow_reconciliation()
            ),
            enrichment_eval.evaluate_seasonality(self._enrichment_reader.observe_seasonality()),
            enrichment_eval.evaluate_company_fundamentals(
                self._enrichment_reader.observe_company_fundamentals()
            ),
            enrichment_eval.evaluate_analyst_cache(self._enrichment_reader.observe_analyst_cache()),
            enrichment_eval.evaluate_insider_cache(self._enrichment_reader.observe_insider_cache()),
            enrichment_eval.evaluate_corporate_action_linkage(
                self._enrichment_reader.observe_corporate_action_linkage()
            ),
            enrichment_eval.evaluate_forward_estimates(
                self._enrichment_reader.observe_forward_estimates()
            ),
            enrichment_eval.evaluate_ticker_notation_cache(
                self._enrichment_reader.observe_ticker_notation()
            ),
            enrichment_eval.evaluate_stock_meta(self._enrichment_reader.observe_stock_meta()),
            artifact_eval.evaluate_candidate_observations_identity(
                self._artifact_reader.observe_candidate_observations_identity()
            ),
            artifact_eval.evaluate_signal_forward_labels_linkage(
                self._artifact_reader.observe_signal_forward_labels_linkage()
            ),
            artifact_eval.evaluate_market_context_snapshot_identity(
                self._artifact_reader.observe_market_context_snapshot_identity()
            ),
            artifact_eval.evaluate_regime_observations_identity(
                self._artifact_reader.observe_regime_observations_identity()
            ),
            artifact_eval.evaluate_learning_observations_risk_pit(
                self._artifact_reader.observe_learning_observations_risk_pit()
            ),
        ):
            checks.append(check)
            findings.extend(check_findings)

        status = aggregate_status(c.status for c in checks)
        return AuditSourceReconciliationResponse(
            artifact_type=self._ARTIFACT_TYPE,
            schema_version=self._SCHEMA_VERSION,
            generated_at=self._clock(),
            status=status,
            checks=tuple(checks),
            findings=tuple(findings),
        )


def _default_clock() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
