"""Optional evidence assembly for swing analysis workflow.

Layer: Application

Builds the best-effort evidence sections (setup evidence, flow confirmation,
setup phase, strategy evidence, institutional accumulation, ticker profile,
sector context, company quality, corporate action risk). Each section is
independent: a failure appends a warning and does not abort the workflow.
Extracted from `SwingAnalysisWorkflowUseCase` to keep the use case as
orchestration only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Callable

from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.services.swing_analysis_market_helpers import (
    benchmark_return_from_repository,
)

if TYPE_CHECKING:
    from src.application.services.flow_confirmation_evidence_builder import (
        FlowConfirmationEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.use_case.assess_corporate_action_event_risk_use_case import (
        AssessCorporateActionEventRiskUseCase,
    )
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.corporate_action_event_risk import (
        CorporateActionRiskAssessment,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


@dataclass(frozen=True)
class SwingAnalysisEvidenceBuildResult:
    setup_evidence: "SetupEvidence | None"
    flow_confirmation_evidence: "FlowConfirmationEvidence | None"
    setup_phase: "SetupPhaseSnapshot | None"
    strategy_rule_evidence: "StrategyEvidence | None"
    institutional_accumulation_evidence: "InstitutionalAccumulationEvidence | None"
    ticker_profile_snapshot: "TickerProfileSnapshot | None"
    sector_context_evidence: "SectorContextEvidence | None"
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
        flow_confirmation_builder: "FlowConfirmationEvidenceBuilder",
        candidate_observations_repository: "CandidateObservationsRepository | None",
        signal_engine: "SignalEngine | None",
        corporate_action_risk_use_case: "AssessCorporateActionEventRiskUseCase | None",
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._flow_confirmation_builder = flow_confirmation_builder
        self._candidate_observations_repo = candidate_observations_repository
        self._signal_engine = signal_engine
        self._corporate_action_risk_use_case = corporate_action_risk_use_case
        self._ticker_profile_classifier_factory = ticker_profile_classifier_factory

    def build(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        benchmark: str,
        candles: list[Any],
        accumulation_candidate: Any | None,
        setup_eval: Any | None,
        setup_name: str | None,
        strategy_name: str | None,
        swing_config: Any,
    ) -> SwingAnalysisEvidenceBuildResult:
        warnings: list[str] = []

        setup_evidence = None
        if accumulation_candidate is not None and setup_eval is not None:
            try:
                from src.application.services.candle_provenance import (
                    resolve_candle_source,
                )
                from src.application.services.setup_evidence_builder import (
                    SetupEvidenceBuilder,
                )

                candle_source = resolve_candle_source(
                    self._market_repo,
                    ticker=ticker,
                    as_of_date=candles[-1].date,
                )
                setup_evidence = SetupEvidenceBuilder().build(
                    accumulation_candidate,
                    setup_eval,
                    rs_vs_ihsg_5d=None,
                    volume_trend_ratio=None,
                    candle_source=candle_source,
                    analysis_date=snapshot_date,
                )
            except Exception as exc:
                warnings.append(f"Setup evidence unavailable: {exc}")

        flow_confirmation_evidence = None
        if accumulation_candidate is not None:
            try:
                flow_confirmation_evidence = self._flow_confirmation_builder.build(
                    accumulation_candidate,
                    analysis_date=snapshot_date,
                )
            except Exception as exc:
                warnings.append(f"Flow confirmation evidence unavailable: {exc}")

        setup_phase = None
        if setup_eval is not None:
            try:
                from src.application.services.setup_phase_detector import (
                    SetupPhaseConfig,
                    SetupPhaseDetector,
                )
                from src.application.services.setup_phase_history import (
                    load_previous_setup_phases,
                )

                setup_phase_config = getattr(
                    swing_config,
                    "setup_phase_config",
                    SetupPhaseConfig(),
                )
                previous_phases = load_previous_setup_phases(
                    self._candidate_observations_repo,
                    ticker=ticker,
                    before_date=snapshot_date,
                    setup_family=setup_name,
                )
                setup_phase = SetupPhaseDetector().detect(
                    candles=candles,
                    setup_eval=setup_eval,
                    setup_evidence=setup_evidence,
                    flow_evidence=flow_confirmation_evidence,
                    setup_family=setup_name,
                    previous_phases=previous_phases,
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
                    loader=StrategyLoader(registry=self._registry),
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
            from src.application.services.institutional_accumulation_evidence_builder import (
                InstitutionalAccumulationEvidenceBuilder,
                InstitutionalAccumulationEvidenceRequest,
            )

            ia_start_date = snapshot_date - timedelta(days=45)
            broker_daily_flows = tuple(
                self._broker_repo.get_broker_daily_flows(
                    ticker, start_date=ia_start_date, end_date=snapshot_date
                )
            )
            foreign_flow_points = tuple(
                self._broker_repo.get_foreign_flow_points(
                    ticker, start_date=ia_start_date, end_date=snapshot_date
                )
            )
            broker_summaries = tuple(
                self._broker_repo.get_broker_summaries(
                    ticker, start_date=ia_start_date, end_date=snapshot_date
                )
            )
            institutional_accumulation_evidence = (
                InstitutionalAccumulationEvidenceBuilder.from_yaml().build(
                    InstitutionalAccumulationEvidenceRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        broker_daily_flows=broker_daily_flows,
                        foreign_flow_points=foreign_flow_points,
                        broker_summaries=broker_summaries,
                        bandar_snapshot=(
                            accumulation_candidate.bandar_detector
                            if accumulation_candidate is not None
                            else None
                        ),
                        candles=tuple(candles),
                    )
                )
            )
        except Exception as exc:
            warnings.append(f"Institutional accumulation evidence unavailable: {exc}")

        ticker_profile_snapshot = None
        if self._ticker_profile_classifier_factory is not None:
            try:
                from decimal import Decimal as _Decimal

                from src.application.dto.ticker_profile import TickerProfileRequest

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
                classifier = self._ticker_profile_classifier_factory()
                ticker_profile_snapshot = classifier.classify(
                    TickerProfileRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        candles=tuple(candles),
                        broker_daily_flows=broker_daily_flows,
                        broker_summaries=broker_summaries,
                        market_cap_idr=tp_market_cap_idr,
                        sector=tp_sector,
                        sub_sector=tp_sub_sector,
                    )
                )
            except Exception as exc:
                warnings.append(f"Ticker profile classification unavailable: {exc}")

        sector_context_evidence = None
        try:
            from src.application.services.sector_context_evidence_builder import (
                SectorContextEvidenceBuilder,
                SectorContextRequest,
            )

            sc_builder = SectorContextEvidenceBuilder.from_yaml()
            sc_sector = (
                accumulation_candidate.ticker_notation.sector
                if accumulation_candidate is not None
                and accumulation_candidate.ticker_notation is not None
                else None
            ) or (
                ticker_profile_snapshot.sector if ticker_profile_snapshot is not None else None
            )
            peer_tickers = sc_builder.peers_for_ticker(ticker)
            peer_candles: dict[str, list] = {}
            for peer in peer_tickers:
                try:
                    pc = self._market_repo.get_candles(peer)
                    if pc:
                        peer_candles[peer] = list(pc)
                except Exception:
                    pass
            ihsg_20d_return = benchmark_return_from_repository(
                self._market_repo,
                benchmark=benchmark,
                end_date=snapshot_date,
                lookback=20,
                min_valid=18,
            )
            sector_context_evidence = sc_builder.build(
                SectorContextRequest(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    sector=sc_sector,
                    ticker_candles=tuple(candles),
                    peer_candles=peer_candles,
                    ihsg_20d_return=ihsg_20d_return,
                )
            )
        except Exception as exc:
            warnings.append(f"Sector context evidence unavailable: {exc}")

        # DIAGNOSTIC-only company-quality / ticker-alpha conviction evidence.
        # Built from the same enrichment already loaded on accumulation_candidate;
        # no extra fetch. Feeds the Alpha/Trigger company_quality_context slot with
        # zero effective score authority (DIAGNOSTIC → effective_weight 0.0).
        company_quality_context_evidence = None
        if accumulation_candidate is not None and self._signal_engine is not None:
            try:
                from src.application.services.company_quality_context_evidence_builder import (
                    CompanyQualityContextEvidenceBuilder,
                    CompanyQualityContextRequest,
                )

                _cq_ctx = build_signal_context_from_candidate(
                    ticker=ticker,
                    snapshot_date=snapshot_date,
                    candidate=accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
                company_quality_context_evidence = (
                    CompanyQualityContextEvidenceBuilder.from_yaml().build(
                        CompanyQualityContextRequest(
                            ticker=ticker,
                            snapshot_date=snapshot_date,
                            signal_context=_cq_ctx,
                        )
                    )
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
                    )
                ).assessment
            except Exception as exc:
                warnings.append(f"Corporate action event-risk unavailable: {exc}")

        return SwingAnalysisEvidenceBuildResult(
            setup_evidence=setup_evidence,
            flow_confirmation_evidence=flow_confirmation_evidence,
            setup_phase=setup_phase,
            strategy_rule_evidence=strategy_rule_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
            ticker_profile_snapshot=ticker_profile_snapshot,
            sector_context_evidence=sector_context_evidence,
            company_quality_context_evidence=company_quality_context_evidence,
            corporate_action_risk=corporate_action_risk,
            broker_daily_flows=broker_daily_flows,
            broker_summaries=broker_summaries,
            warnings=tuple(warnings),
        )
