"""Optional evidence assembly for swing analysis workflow.

Layer: Application

Coordinates the best-effort evidence sections (setup evidence, flow
confirmation, setup phase, strategy evidence, institutional accumulation,
ticker profile, sector context, company quality, corporate action risk).
Each section is independent: a failure appends a warning and does not abort
the workflow. Extracted from `SwingAnalysisWorkflowUseCase` to keep the use
case as orchestration only. Repository data loading and per-family evidence
assembly live in dedicated collaborators (`CandidateEvidenceDataLoader` and
the `candidate_*_evidence_assembler` modules) shared with
`AccumulationCandidateEvidenceBuilder`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Callable

from src.application.ports.rules_loader import RulesLoader
from src.application.services.candidate_company_quality_context_evidence_assembler import (
    CandidateCompanyQualityContextEvidenceAssembler,
)
from src.application.services.candidate_evidence_data_loader import (
    CandidateEvidenceDataLoader,
)
from src.application.services.candidate_institutional_accumulation_evidence_assembler import (
    CandidateInstitutionalAccumulationEvidenceAssembler,
)
from src.application.services.candidate_sector_context_evidence_assembler import (
    CandidateSectorContextEvidenceAssembler,
)
from src.application.services.candidate_sector_macro_context_evidence_assembler import (
    CandidateSectorMacroContextEvidenceAssembler,
)
from src.application.services.candidate_setup_phase_evidence_assembler import (
    CandidateSetupPhaseEvidenceAssembler,
)
from src.application.services.candidate_ticker_profile_evidence_assembler import (
    CandidateTickerProfileEvidenceAssembler,
)
from src.application.services.strategy_loader import StrategyLoader

if TYPE_CHECKING:
    from src.application.dto.accumulation_screen import (
        AccumulationCandidateEvaluationResult,
    )
    from src.application.dto.built_evidence import BuiltFlowEvidence, BuiltSetupEvidence
    from src.application.ports.macro_calendar_repository import MacroCalendarRepository
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.flow_confirmation_evidence_builder import (
        FlowConfirmationEvidenceBuilder,
    )
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceBuilder,
    )
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.sector_macro_context_evidence_builder import (
        SectorMacroContextEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.use_case.assess_corporate_action_event_risk_use_case import (
        AssessCorporateActionEventRiskUseCase,
    )
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.learning_artifact_repositories import (
        LearningObservationRepository,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.corporate_action_event_risk import (
        CorporateActionRiskAssessment,
    )
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


@dataclass(frozen=True)
class SwingAnalysisEvidenceBuildResult:
    # Complete built evidence (evidence + exact consumed-row provenance,
    # ADR-041 CANONICAL-EVIDENCE-BOUNDARY) — never unwrapped to a loose
    # evidence value here. Presentation/diagnostic DTOs may read
    # `.evidence` off these; canonical scoring must receive the whole
    # object until availability has been attached.
    built_setup_evidence: "BuiltSetupEvidence | None"
    built_flow_evidence: "BuiltFlowEvidence | None"
    setup_phase: "SetupPhaseSnapshot | None"
    strategy_rule_evidence: "StrategyEvidence | None"
    institutional_accumulation_evidence: "InstitutionalAccumulationEvidence | None"
    ticker_profile_snapshot: "TickerProfileSnapshot | None"
    sector_context_evidence: "SectorContextEvidence | None"
    sector_macro_context_evidence: "SectorMacroContextEvidence | None"
    company_quality_context_evidence: "CompanyQualityContextEvidence | None"
    corporate_action_risk: "CorporateActionRiskAssessment | None"
    broker_daily_flows: tuple
    broker_summaries: tuple
    warnings: tuple[str, ...]


class SwingAnalysisEvidenceBuilder:
    """Builds optional, best-effort evidence sections for swing analysis."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        registry: Any,
        rules_loader: RulesLoader,
        flow_confirmation_builder: "FlowConfirmationEvidenceBuilder",
        candidate_observations_repository: "LearningObservationRepository | None",
        signal_engine: "SignalEngine | None",
        corporate_action_risk_use_case: "AssessCorporateActionEventRiskUseCase | None",
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
        institutional_accumulation_config_factory: (
            Callable[[], InstitutionalAccumulationConfig] | None
        ) = None,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder] | None = None,
        sector_macro_context_builder_factory: (
            Callable[[], SectorMacroContextEvidenceBuilder] | None
        ) = None,
        company_quality_context_builder_factory: (
            Callable[[], CompanyQualityContextEvidenceBuilder] | None
        ) = None,
        macro_calendar_repository: "MacroCalendarRepository | None" = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._rules_loader = rules_loader
        self._flow_confirmation_builder = flow_confirmation_builder
        self._candidate_observations_repo = candidate_observations_repository
        self._signal_engine = signal_engine
        self._corporate_action_risk_use_case = corporate_action_risk_use_case
        self._ticker_profile_classifier_factory = ticker_profile_classifier_factory
        self._sector_context_builder_factory = _normalize_sector_context_factory(
            sector_context_builder_factory
        )
        self._sector_macro_context_builder_factory = _normalize_sector_macro_context_factory(
            sector_macro_context_builder_factory
        )

        self._data_loader = CandidateEvidenceDataLoader(
            market_repository,
            broker_repository,
            macro_calendar_repository=macro_calendar_repository,
        )
        self._setup_phase_assembler = CandidateSetupPhaseEvidenceAssembler(
            market_repository, candidate_observations_repository
        )
        self._institutional_assembler = CandidateInstitutionalAccumulationEvidenceAssembler(
            _normalize_institutional_accumulation_factory(institutional_accumulation_config_factory)
        )
        self._ticker_profile_assembler = CandidateTickerProfileEvidenceAssembler(
            ticker_profile_classifier_factory
        )
        self._sector_context_assembler = CandidateSectorContextEvidenceAssembler()
        self._sector_macro_context_assembler = CandidateSectorMacroContextEvidenceAssembler()
        self._company_quality_assembler = CandidateCompanyQualityContextEvidenceAssembler(
            _normalize_company_quality_context_factory(company_quality_context_builder_factory)
        )

    def build(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        benchmark: str,
        candles: list[Any],
        accumulation_evaluation: "AccumulationCandidateEvaluationResult | None",
        setup_eval: Any | None,
        setup_name: str | None,
        strategy_name: str | None,
        swing_config: Any,
        as_of_fetched_at: str | None = None,
    ) -> SwingAnalysisEvidenceBuildResult:
        """`as_of_fetched_at` (ISO timestamp, DQ-002G): the workflow's
        resolved decision timestamp (`EffectiveMarketSession.decision_at`),
        forwarded to `AssessCorporateActionEventRiskUseCase` so a historical
        `analyze swing` run cannot see a corporate-action calendar row that
        was synced after that historical decision point. `None` (default)
        preserves prior unfiltered behavior."""
        warnings: list[str] = []
        accumulation_candidate = (
            accumulation_evaluation.candidate if accumulation_evaluation is not None else None
        )

        built_setup_evidence: "BuiltSetupEvidence | None" = None
        setup_evidence = None
        if accumulation_candidate is not None and setup_eval is not None:
            try:
                built_setup_evidence = self._setup_phase_assembler.build_setup_evidence(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    candles=candles,
                    candidate=accumulation_candidate,
                    setup_eval=setup_eval,
                )
                setup_evidence = built_setup_evidence.evidence
            except (ValueError, TypeError):
                raise
            except Exception as exc:
                warnings.append(f"Setup evidence unavailable: {exc}")

        built_flow_evidence: "BuiltFlowEvidence | None" = None
        flow_confirmation_evidence = None
        if accumulation_evaluation is not None:
            try:
                # The exact rows AccumulationCandidateEvaluator already
                # consumed for this candidate — never a second, independent
                # repository read (ADR-041 CANONICAL-EVIDENCE-BOUNDARY): a
                # second read could return different rows than the ones the
                # candidate's own foreign-flow fields were actually computed
                # from.
                built_flow_evidence = self._flow_confirmation_builder.build(
                    accumulation_candidate,
                    analysis_date=snapshot_date,
                    consumed_broker_summaries=(accumulation_evaluation.consumed_broker_summaries),
                    consumed_broker_daily_flows=(
                        accumulation_evaluation.consumed_broker_daily_flows
                    ),
                )
                flow_confirmation_evidence = built_flow_evidence.evidence
            except (ValueError, TypeError):
                raise
            except Exception as exc:
                warnings.append(f"Flow confirmation evidence unavailable: {exc}")

        setup_phase = None
        if setup_eval is not None:
            try:
                from src.application.services.setup_phase_detector import SetupPhaseConfig

                setup_phase_config = getattr(
                    swing_config,
                    "setup_phase_config",
                    SetupPhaseConfig(),
                )
                setup_phase = self._setup_phase_assembler.detect_setup_phase(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    candles=candles,
                    setup_eval=setup_eval,
                    setup_evidence=setup_evidence,
                    flow_evidence=flow_confirmation_evidence,
                    setup_family=setup_name,
                    config=setup_phase_config,
                )
            except Exception as exc:
                warnings.append(f"Setup phase unavailable: {exc}")

        strategy_rule_evidence = None
        if strategy_name is not None:
            try:
                from src.application.services.strategy_evidence_builder import (
                    StrategyEvidenceBuilder,
                    StrategyEvidenceRequest,
                )

                strategy_rule_evidence = StrategyEvidenceBuilder(
                    registry=self._registry,
                    loader=StrategyLoader(rules_loader=self._rules_loader, registry=self._registry),
                ).build(
                    StrategyEvidenceRequest(
                        ticker=ticker,
                        strategy_name=strategy_name,
                        candles=tuple(candles),
                        snapshot_date=snapshot_date,
                        setup_family=setup_name,
                        setup_phase=setup_phase,
                    )
                )
            except Exception as exc:
                warnings.append(f"Strategy evidence unavailable: {exc}")

        broker_daily_flows: tuple = ()
        broker_summaries: tuple = ()
        institutional_accumulation_evidence = None
        try:
            institutional_inputs = self._data_loader.load_institutional_inputs(
                ticker=ticker, snapshot_date=snapshot_date, candles=candles
            )
            broker_daily_flows = institutional_inputs.broker_daily_flows
            broker_summaries = institutional_inputs.broker_summaries
            institutional_accumulation_evidence = self._institutional_assembler.assemble(
                ticker=ticker,
                snapshot_date=snapshot_date,
                inputs=institutional_inputs,
                bandar_snapshot=(
                    accumulation_candidate.bandar_detector
                    if accumulation_candidate is not None
                    else None
                ),
            )
        except Exception as exc:
            warnings.append(f"Institutional accumulation evidence unavailable: {exc}")

        ticker_profile_snapshot = None
        if self._ticker_profile_classifier_factory is not None:
            try:
                from decimal import Decimal as _Decimal

                tp_market_cap_idr: _Decimal | None = None
                if (
                    accumulation_candidate is not None
                    and accumulation_candidate.fundamentals is not None
                    and accumulation_candidate.fundamentals.market_cap_idr is not None
                ):
                    tp_market_cap_idr = _Decimal(
                        str(accumulation_candidate.fundamentals.market_cap_idr)
                    )
                tp_sector = (
                    accumulation_candidate.ticker_notation.sector
                    if accumulation_candidate is not None
                    and accumulation_candidate.ticker_notation is not None
                    else None
                )
                tp_sub_sector = (
                    accumulation_candidate.ticker_notation.sub_sector
                    if accumulation_candidate is not None
                    and accumulation_candidate.ticker_notation is not None
                    else None
                )
                ticker_profile_inputs = self._data_loader.load_ticker_profile_inputs(
                    ticker=ticker, snapshot_date=snapshot_date, candles=candles
                )
                ticker_profile_snapshot = self._ticker_profile_assembler.assemble(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    inputs=ticker_profile_inputs,
                    market_cap_idr=tp_market_cap_idr,
                    sector=tp_sector,
                    sub_sector=tp_sub_sector,
                )
            except Exception as exc:
                warnings.append(f"Ticker profile classification unavailable: {exc}")

        sector_context_evidence = None
        try:
            sc_builder = self._sector_context_builder_factory()
            sc_sector = (
                accumulation_candidate.ticker_notation.sector
                if accumulation_candidate is not None
                and accumulation_candidate.ticker_notation is not None
                else None
            ) or (ticker_profile_snapshot.sector if ticker_profile_snapshot is not None else None)
            peer_tickers = sc_builder.peers_for_ticker(ticker)
            sector_inputs = self._data_loader.load_sector_context_inputs(
                ticker=ticker,
                snapshot_date=snapshot_date,
                sector=sc_sector,
                peer_tickers=peer_tickers,
                benchmark=benchmark,
                ticker_candles=candles,
            )
            sector_context_evidence = self._sector_context_assembler.assemble(
                builder=sc_builder,
                ticker=ticker,
                snapshot_date=snapshot_date,
                sector=sc_sector,
                inputs=sector_inputs,
            )
        except Exception as exc:
            warnings.append(f"Sector context evidence unavailable: {exc}")

        sector_macro_context_evidence = None
        try:
            smc_builder = self._sector_macro_context_builder_factory()
            sc_group_builder = self._sector_context_builder_factory()
            sector_group = smc_builder.resolve_sector_group(
                sc_group_builder.sector_groups_for_ticker(ticker)
            )
            series_tickers = smc_builder.config.series_for_group(sector_group)
            policy_series = smc_builder.config.policy_series_for_group(sector_group)
            policy_lookback = smc_builder.config.max_policy_lookback_days_for_group(sector_group)
            smc_inputs = self._data_loader.load_sector_macro_context_inputs(
                series_tickers=series_tickers,
                snapshot_date=snapshot_date,
                policy_series=policy_series,
                policy_lookback_days=policy_lookback,
            )
            sector_macro_context_evidence = self._sector_macro_context_assembler.assemble(
                builder=smc_builder,
                ticker=ticker,
                snapshot_date=snapshot_date,
                sector_group=sector_group,
                inputs=smc_inputs,
            )
        except Exception as exc:
            warnings.append(f"Sector macro context evidence unavailable: {exc}")

        # DIAGNOSTIC-only company-quality / ticker-alpha conviction evidence.
        # Built from the same enrichment already loaded on accumulation_candidate;
        # no extra fetch. Feeds the Alpha/Trigger company_quality_context slot with
        # zero effective score authority (DIAGNOSTIC → effective_weight 0.0).
        company_quality_context_evidence = None
        if accumulation_candidate is not None and self._signal_engine is not None:
            try:
                company_quality_context_evidence = self._company_quality_assembler.assemble(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    candidate=accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
            except Exception as exc:
                warnings.append(f"Company quality context evidence unavailable: {exc}")

        # Corporate calendar event-risk context — display/diagnostics only. Never
        # consumed by SignalEngine, RiskEngine, or AssessTradeSetupUseCase; the
        # verdict chain remains exclusively SignalEngine + RiskEngine -> TradeSetup.
        corporate_action_risk = None
        if self._corporate_action_risk_use_case is not None:
            try:
                from src.application.use_case.assess_corporate_action_event_risk_use_case import (
                    AssessCorporateActionEventRiskRequest,
                )

                corporate_action_risk = self._corporate_action_risk_use_case.execute(
                    AssessCorporateActionEventRiskRequest(
                        ticker=ticker,
                        as_of_date=snapshot_date,
                        as_of_fetched_at=as_of_fetched_at,
                    )
                ).assessment
            except Exception as exc:
                warnings.append(f"Corporate action event-risk unavailable: {exc}")

        return SwingAnalysisEvidenceBuildResult(
            built_setup_evidence=built_setup_evidence,
            built_flow_evidence=built_flow_evidence,
            setup_phase=setup_phase,
            strategy_rule_evidence=strategy_rule_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
            ticker_profile_snapshot=ticker_profile_snapshot,
            sector_context_evidence=sector_context_evidence,
            sector_macro_context_evidence=sector_macro_context_evidence,
            company_quality_context_evidence=company_quality_context_evidence,
            corporate_action_risk=corporate_action_risk,
            broker_daily_flows=broker_daily_flows,
            broker_summaries=broker_summaries,
            warnings=tuple(warnings),
        )


def _normalize_sector_macro_context_factory(
    builder_factory: "Callable[[], SectorMacroContextEvidenceBuilder] | None",
) -> "Callable[[], SectorMacroContextEvidenceBuilder]":
    if builder_factory is not None:
        return builder_factory

    def _build() -> "SectorMacroContextEvidenceBuilder":
        from src.application.services.sector_macro_context_evidence_builder import (
            SectorMacroContextConfig,
            SectorMacroContextEvidenceBuilder,
        )

        # Empty maps → deterministic unavailable for every ticker.
        return SectorMacroContextEvidenceBuilder(
            SectorMacroContextConfig.from_mapping(
                {
                    "sector_macro_context": {
                        "factor_library": {
                            "_placeholder": {
                                "series": "MTF=F",
                                "thresholds": {
                                    "supportive_min": 0.05,
                                    "headwind_max": -0.05,
                                },
                            }
                        },
                        "sector_maps": {},
                    }
                }
            )
        )

    return _build


def _normalize_sector_context_factory(
    builder_factory: "Callable[[], SectorContextEvidenceBuilder] | None",
) -> "Callable[[], SectorContextEvidenceBuilder]":
    if builder_factory is not None:
        return builder_factory

    def _build() -> "SectorContextEvidenceBuilder":
        from src.application.services.sector_context_evidence_builder import (
            SectorContextConfig,
            SectorContextEvidenceBuilder,
        )

        return SectorContextEvidenceBuilder(SectorContextConfig.from_mapping({}), {})

    return _build


def _normalize_institutional_accumulation_factory(
    config_factory: Callable[[], "InstitutionalAccumulationConfig"] | None,
) -> Callable[[], "InstitutionalAccumulationEvidenceBuilder"]:
    def _build() -> "InstitutionalAccumulationEvidenceBuilder":
        from src.application.services.institutional_accumulation_evidence_builder import (
            InstitutionalAccumulationEvidenceBuilder,
        )

        if config_factory is not None:
            return InstitutionalAccumulationEvidenceBuilder(config_factory())
        return InstitutionalAccumulationEvidenceBuilder()

    return _build


def _normalize_company_quality_context_factory(
    builder_factory: Callable[[], "CompanyQualityContextEvidenceBuilder"] | None,
) -> Callable[[], "CompanyQualityContextEvidenceBuilder"]:
    if builder_factory is not None:
        return builder_factory

    def _build() -> "CompanyQualityContextEvidenceBuilder":
        from src.application.services.company_quality_context_evidence_builder import (
            CompanyQualityContextConfig,
            CompanyQualityContextEvidenceBuilder,
        )

        return CompanyQualityContextEvidenceBuilder(CompanyQualityContextConfig.from_mapping({}))

    return _build
