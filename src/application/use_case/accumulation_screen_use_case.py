"""
AccumulationScreenUseCase — multi-stock foreign accumulation screener.

Scans a list of tickers for sustained foreign investor accumulation patterns.
Foreign-flow scoring is delegated to ScoreForeignFlowUseCase;
this use case owns orchestration, filtering, enrichment, and sorting.

Intraday vs Swing usage:
  This screener produces a SWING WATCHLIST (5–20 day horizon).
  For intraday timing, cross-reference with `saham screen pre-open`.

Layer: Application
Depends on: Domain ports only — no infrastructure imports
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.ports.corporate_action_repository import CorporateActionRepository
from src.application.ports.rules_loader import RulesLoader
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.accumulation_risk_funnel import AccumulationRiskFunnel
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowUseCase,
)
from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.forward_estimates_provider import ForwardEstimatesProvider
from src.domain.ports.fundamentals_provider import FundamentalsProvider
from src.domain.ports.insider_activity_provider import InsiderActivityProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.seasonality_provider import SeasonalityProvider
from src.domain.ports.shareholding_provider import ShareholdingProvider
from src.domain.ports.ticker_notation_provider import TickerNotationProvider

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.benchmark_excess_return_calculator import (
        BenchmarkExcessReturnCalculator,
    )
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
    )
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )

# Default setup targets (1:1 R:R, regime-unaware fallback)
_DEFAULT_TAKE_PROFIT = Decimal("5")
_DEFAULT_STOP_LOSS = Decimal("5")
# Regime-specific targets (validated direction: IHSG has documented regime cycles)
# MCE vocabulary (RISK_ON/NEUTRAL/VOLATILE/RISK_OFF).
_REGIME_TARGETS: dict[str, tuple[Decimal, Decimal]] = {
    "RISK_ON": (Decimal("8"), Decimal("4")),  # 2:1 R:R — trending market
    "NEUTRAL": (Decimal("5"), Decimal("5")),  # 1:1 R:R — range-bound
    "VOLATILE": (Decimal("3"), Decimal("3")),  # tight — minimize exposure
    "RISK_OFF": (Decimal("3"), Decimal("3")),  # capital preservation
}


def resolve_setup_targets(
    regime: str | None,
    config: Any | None = None,
) -> tuple[Decimal, Decimal]:
    """Return (take_profit_pct, stop_loss_pct) for the foreign-bounce setup.

    Precedence: YAML config overrides > regime defaults > hardcoded fallback.
    All values are in percentage points (e.g. Decimal("5") = 5%).
    """
    if config:
        targets = getattr(config, "setup_targets", None)
        if targets is None and isinstance(config, dict):
            targets = config.get("setup_targets", config)
        targets = targets or {}
        regime_key = (regime or "default").lower()
        tier = targets.get(regime_key) or targets.get("default", {})
        if tier:
            if isinstance(tier, dict):
                tp = tier.get("take_profit_pct")
                sl = tier.get("stop_loss_pct")
            else:
                tp = getattr(tier, "take_profit_pct", None)
                sl = getattr(tier, "stop_loss_pct", None)
            if tp is not None and sl is not None:
                return Decimal(str(tp)), Decimal(str(sl))

    if regime and regime.upper() in _REGIME_TARGETS:
        return _REGIME_TARGETS[regime.upper()]

    return _DEFAULT_TAKE_PROFIT, _DEFAULT_STOP_LOSS


def _trade_action_rank(candidate: "accumulation_dto.AccumulationCandidate") -> int:
    if candidate.trade_setup is None:
        return 0
    action = candidate.trade_setup.action.value
    return {
        "ENTER": 5,
        "WATCH": 4,
        "AVOID": 2,
        "BLOCKED_EXECUTION": 1,
        "BLOCKED_STRUCTURAL": 0,
    }.get(action, 0)


def _screen_sort_key(
    candidate: "accumulation_dto.AccumulationCandidate",
) -> tuple[float, float, float, float]:
    """Default screener ordering: verdict, signal, foreign-flow score, seasonality."""
    return (
        float(_trade_action_rank(candidate)),
        float(candidate.signal_assessment.assessment.score if candidate.signal_assessment else 0),
        candidate.foreign_flow_score,
        candidate.seasonal_edge.score if candidate.seasonal_edge else 0.0,
    )


class AccumulationScreenUseCase:
    """
    Scan multiple tickers for foreign accumulation patterns.

    Reads from local repositories only — no network calls.
    All data must be fetched beforehand via `saham fetch market`.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        corporate_action_repo: "CorporateActionRepository | None" = None,
        seasonality_provider: "SeasonalityProvider | None" = None,
        insider_activity_provider: "InsiderActivityProvider | None" = None,
        analyst_consensus_provider: "AnalystConsensusProvider | None" = None,
        forward_estimates_provider: "ForwardEstimatesProvider | None" = None,
        shareholding_provider: "ShareholdingProvider | None" = None,
        bandar_detector_provider: "BandarDetectorProvider | None" = None,
        fundamentals_provider: "FundamentalsProvider | None" = None,
        ticker_notation_provider: "TickerNotationProvider | None" = None,
        idx_groups: "dict[str, list[str]] | None" = None,
        risk_use_case: "AssessRiskUseCase | None" = None,
        signal_engine: "SignalEngine | None" = None,
        candidate_observations_repository: "CandidateObservationsRepository | None" = None,
        foreign_flow_score_use_case: ScoreForeignFlowUseCase | None = None,
        derived_feature_policy: accumulation_dto.AccumulationDerivedFeaturePolicy | None = None,
        swing_setup_catalog: "SwingSetupCatalogConfig | None" = None,
        primary_setup_family_resolver: "PrimarySetupFamilyResolver | None" = None,
        benchmark_excess_return_calculator: "BenchmarkExcessReturnCalculator | None" = None,
        *,
        indicator_registry: "IndicatorRegistry",
        rules_loader: RulesLoader,
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
        institutional_accumulation_config_factory: (
            Callable[[], InstitutionalAccumulationConfig] | None
        ) = None,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder] | None = None,
        company_quality_context_builder_factory: (
            Callable[[], CompanyQualityContextEvidenceBuilder] | None
        ) = None,
    ) -> None:
        from src.application.services.flow_confirmation_evidence_builder import (
            FlowConfirmationEvidenceBuilder,
        )
        from src.application.services.primary_setup_family_resolver import (
            PrimarySetupFamilyResolver as _PrimarySetupFamilyResolver,
        )
        from src.application.services.benchmark_excess_return_calculator import (
            BenchmarkExcessReturnCalculator as _BenchmarkExcessReturnCalculator,
        )
        from src.application.services.signal_engine import SignalEngine as _SignalEngine

        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._risk_use_case = risk_use_case
        self._signal_engine = signal_engine or _SignalEngine()
        self._candidate_observations_repo = candidate_observations_repository
        self._foreign_flow_score_uc = foreign_flow_score_use_case or ScoreForeignFlowUseCase()
        self._derived_features = (
            derived_feature_policy or accumulation_dto.AccumulationDerivedFeaturePolicy()
        )
        self._swing_setup_catalog = swing_setup_catalog
        self._setup_family_resolver = primary_setup_family_resolver or _PrimarySetupFamilyResolver()
        self._benchmark_excess_return_calculator = (
            benchmark_excess_return_calculator or _BenchmarkExcessReturnCalculator()
        )
        self._indicator_registry = indicator_registry
        # Derive weights from the same policy ScoreForeignFlowUseCase uses, so
        # the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            foreign_flow_score_policy=self._foreign_flow_score_uc.policy
        )
        self._candidate_evidence_builder = AccumulationCandidateEvidenceBuilder(
            market_repository=self._market_repo,
            broker_repository=self._broker_repo,
            signal_engine=self._signal_engine,
            candidate_observations_repository=self._candidate_observations_repo,
            swing_setup_catalog=self._swing_setup_catalog,
            primary_setup_family_resolver=self._setup_family_resolver,
            benchmark_excess_return_calculator=self._benchmark_excess_return_calculator,
            indicator_registry=self._indicator_registry,
            rules_loader=rules_loader,
            ticker_profile_classifier_factory=ticker_profile_classifier_factory,
            institutional_accumulation_config_factory=institutional_accumulation_config_factory,
            sector_context_builder_factory=sector_context_builder_factory,
            company_quality_context_builder_factory=company_quality_context_builder_factory,
        )
        self._risk_funnel = (
            AccumulationRiskFunnel(self._risk_use_case) if self._risk_use_case is not None else None
        )
        self._ticker_to_group: dict[str, str] = {}
        if idx_groups:
            for group_name, tickers in idx_groups.items():
                for t in tickers:
                    self._ticker_to_group[t.upper()] = group_name

        from src.application.services.accumulation_candidate_enricher import (
            AccumulationCandidateEnricher,
        )
        from src.application.services.accumulation_candidate_evaluator import (
            AccumulationCandidateEvaluator,
        )
        from src.application.services.accumulation_candidate_signal_assessor import (
            AccumulationCandidateSignalAssessor,
        )
        from src.application.services.accumulation_candidate_structural_filter import (
            AccumulationCandidateStructuralFilter,
        )
        from src.application.services.accumulation_sector_breadth import (
            AccumulationSectorBreadthApplier,
        )

        self._candidate_evaluator = AccumulationCandidateEvaluator(
            broker_repository=self._broker_repo,
            market_repository=self._market_repo,
            derived_feature_policy=self._derived_features,
        )
        self._sector_breadth_applier = AccumulationSectorBreadthApplier(
            ticker_to_group=self._ticker_to_group
        )
        self._structural_filter = AccumulationCandidateStructuralFilter(
            fundamentals_provider=fundamentals_provider,
        )
        self._enricher = AccumulationCandidateEnricher(
            corp_action_repo=corporate_action_repo,
            seasonality_provider=seasonality_provider,
            insider_provider=insider_activity_provider,
            analyst_provider=analyst_consensus_provider,
            shareholding_provider=shareholding_provider,
            bandar_provider=bandar_detector_provider,
            fundamentals_provider=fundamentals_provider,
            ticker_notation_provider=ticker_notation_provider,
            forward_estimates_provider=forward_estimates_provider,
            derived_features=self._derived_features,
        )
        self._signal_assessor = AccumulationCandidateSignalAssessor(
            signal_engine=self._signal_engine,
            flow_confirmation_builder=self._flow_confirmation_builder,
            candidate_evidence_builder=self._candidate_evidence_builder,
            foreign_flow_score_uc=self._foreign_flow_score_uc,
        )

    def execute(
        self,
        request: accumulation_dto.AccumulationScreenRequest,
        *,
        execution_context: SignalEvidenceExecutionContext,
    ) -> accumulation_dto.AccumulationScreenResponse:
        today = request.as_of_date or date.today()
        candidates: list[accumulation_dto.AccumulationCandidate] = []
        # Collects an AccumulationScreenObservationCandidate for ALL evaluated
        # tickers — survivors and filtered-out alike. Rejected records are
        # negative samples for future tuning (Phase 7: "rejected candidates
        # become learnable"). execute() itself never persists these — see
        # RecordAccumulationObservationsUseCase.
        observation_candidates: list[accumulation_dto.AccumulationScreenObservationCandidate] = []
        skipped = 0
        uses_stockbit = False

        effective_session = execution_context.effective_session
        source_availability_use_case = (
            execution_context.source_availability_use_case
        )

        for ticker in request.tickers:
            eval_result = self._candidate_evaluator.evaluate(
                ticker=ticker,
                window_days=request.window_days,
                today=today,
                min_net_buy_days=request.min_net_buy_days,
                rsi_period=request.rsi_period or self._derived_features.rsi_period,
                sma_period=request.sma_period or self._derived_features.trend_sma_period,
                tier1_broker_codes=request.tier1_broker_codes,
                bci_cluster_min_count=request.bci_cluster_min_count,
                bci_stable_min_count=request.bci_stable_min_count,
            )

            if eval_result is None:
                skipped += 1
                continue

            result = eval_result.candidate
            consumed_broker_summaries = eval_result.consumed_broker_summaries
            consumed_broker_daily_flows = eval_result.consumed_broker_daily_flows

            if result.top_brokers is not None:
                uses_stockbit = True

            # Step 1: Structural filter — early pruning before expensive enrichment
            filter_result = self._structural_filter.apply(result, request)

            if filter_result.rejected:
                observation_candidates.append(
                    accumulation_dto.AccumulationScreenObservationCandidate(
                        evaluation_result=eval_result,
                        screen_result=filter_result.screen_result,
                        flow_evidence=None,
                    )
                )
                skipped += 1
                continue

            # Step 2: Provider-backed enrichment
            enrich_result = self._enricher.enrich(
                filter_result.candidate,
                request=request,
                as_of_date=today,
                fundamentals_fetched=filter_result.fundamentals_fetched,
            )
            result = enrich_result.candidate
            result.insider_net_buy_ratio = enrich_result.insider_net_buy_ratio

            # Step 3: Signal assessment, flow evidence, setup phase, classification
            assessment = self._signal_assessor.assess(
                result,
                request=request,
                as_of_date=today,
                consumed_broker_summaries=consumed_broker_summaries,
                consumed_broker_daily_flows=consumed_broker_daily_flows,
                effective_session=effective_session,
                source_availability_use_case=source_availability_use_case,
            )
            result = assessment.candidate

            observation_candidates.append(
                accumulation_dto.AccumulationScreenObservationCandidate(
                    evaluation_result=eval_result,
                    screen_result=assessment.screen_result,
                    flow_evidence=assessment.flow_evidence,
                )
            )
            if assessment.passes:
                candidates.append(result)

        # Phase 3.2: sector breadth post-processing pass
        if request.sector_breadth_enabled and self._ticker_to_group:
            self._sector_breadth_applier.apply(candidates, request)

        # Phase E (Rec 14): post-screening risk funnel — runs only on survivors,
        # not on all 800+ tickers. Reuses already-loaded fundamentals + bandar
        # data from candidates (Rec 15 data sharing — zero extra provider queries).
        if self._risk_funnel is not None:
            self._risk_funnel.run(candidates, today)

        candidates.sort(key=_screen_sort_key, reverse=True)

        return accumulation_dto.AccumulationScreenResponse(
            candidates=candidates,
            screened_at=today,
            window_days=request.window_days,
            total_tickers_checked=len(request.tickers),
            tickers_skipped=skipped,
            provider="stockbit" if uses_stockbit else "idx",
            observation_candidates=observation_candidates,
        )
