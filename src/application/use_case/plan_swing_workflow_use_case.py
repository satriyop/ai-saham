"""
Application workflow coordinator for `saham plan swing`.

Layer: Application
AI usage: Optional sentiment provider, controlled by injected fetcher.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.dto import plan_swing as plan_swing_dto
from src.application.ports.rules_loader import RulesLoader

if TYPE_CHECKING:
    from src.application.ports.macro_calendar_repository import MacroCalendarRepository
    from src.application.services.company_quality_context_evidence_builder import (
        CompanyQualityContextEvidenceBuilder,
    )
    from src.application.services.institutional_flow_config import (
        InstitutionalAccumulationConfig,
    )
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.sector_context_evidence_builder import (
        SectorContextEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.signal_evidence_execution_context_builder import (
        SignalEvidenceExecutionContextBuilder,
    )
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.use_case.assess_corporate_action_event_risk_use_case import (
        AssessCorporateActionEventRiskUseCase,
    )
    from src.domain.value_objects.market_context import MarketContext

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.plan_swing_decision_composer import (
    PlanSwingDecisionComposer,
)
from src.application.services.plan_swing_evidence_builder import (
    PlanSwingEvidenceBuilder,
)
from src.application.services.plan_swing_input_collector import (
    PlanSwingDataUnavailable,
    PlanSwingInputCollector,
)
from src.application.services.plan_swing_optional_evidence_runner import (
    PlanSwingOptionalEvidenceRunner,
)
from src.application.services.plan_swing_response_assembler import (
    PlanSwingResponseAssembler,
)
from src.application.services.plan_swing_risk_trade_setup import (
    PlanSwingRiskTradeSetupComposer,
)
from src.application.services.plan_swing_sizing_service import (
    PlanSwingSizingService,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import RiskGate

__all__ = ["PlanSwingWorkflowUseCase", "PlanSwingDataUnavailable"]


class PlanSwingWorkflowUseCase:
    """Run deterministic swing analysis steps and return structured state."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        registry: Any,
        refresh_data: Callable[..., tuple[str, ...]],
        build_data_freshness: Callable[..., Any],
        build_flow_detail: Callable[..., Any],
        build_broker_detail: Callable[..., Any],
        # Expected signature: (ticker: str, window: int, as_of_date: date) ->
        # AccumulationCandidateEvaluationResult | None. Kept as a flexible
        # ``Callable[..., ...]`` so test fakes may accept **kwargs.
        build_accumulation_candidate_evaluation: Callable[..., Any | None],
        evaluate_setup: Callable[[Any | None, Any | None], Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        load_swing_policy_config: Callable[[], Any],
        resolve_setup_targets: Callable[[str | None, Any], tuple[Decimal, Decimal]],
        rules_loader: RulesLoader,
        signal_evidence_context_builder: "SignalEvidenceExecutionContextBuilder",
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
        signal_engine: "SignalEngine | None" = None,
        risk_engine: "RiskEngine | None" = None,
        candidate_observations_repository: LearningObservationRepository | None = None,
        setup_phase_history_repository: Any | None = None,
        accum_score_policy: AccumScorePolicy | None = None,
        corporate_action_risk_use_case: "AssessCorporateActionEventRiskUseCase | None" = None,
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
        institutional_accumulation_config_factory: (
            Callable[[], InstitutionalAccumulationConfig] | None
        ) = None,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder] | None = None,
        sector_macro_context_builder_factory: Callable[..., Any] | None = None,
        company_quality_context_builder_factory: (
            Callable[[], CompanyQualityContextEvidenceBuilder] | None
        ) = None,
        macro_calendar_repository: "MacroCalendarRepository | None" = None,
        session_resolver: EffectiveMarketSessionResolver | None = None,
        live_signal_evidence_context_use_case: Any | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate_evaluation = build_accumulation_candidate_evaluation
        self._evaluate_setup = evaluate_setup
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._load_swing_policy_config = load_swing_policy_config
        self._resolve_setup_targets = resolve_setup_targets
        self._rules_loader = rules_loader
        self._evaluate_market_context = evaluate_market_context
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []
        self._signal_engine = signal_engine
        self._risk_engine = risk_engine
        self._candidate_observations_repo = candidate_observations_repository
        self._corporate_action_risk_use_case = corporate_action_risk_use_case
        # Derive weights from the same policy ScoreAccumUseCase/screener
        # use, so the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            accum_score_policy=accum_score_policy
        )
        self._risk_trade_setup_composer = PlanSwingRiskTradeSetupComposer(
            market_repository=market_repository,
            registry=registry,
            structural_gates=self._structural_gates,
            execution_gates=self._execution_gates,
            signal_engine=signal_engine,
            risk_engine=risk_engine,
        )
        self._evidence_builder = PlanSwingEvidenceBuilder(
            market_repository=market_repository,
            broker_repository=broker_repository,
            registry=registry,
            rules_loader=rules_loader,
            flow_confirmation_builder=self._flow_confirmation_builder,
            candidate_observations_repository=candidate_observations_repository,
            setup_phase_history_repository=setup_phase_history_repository,
            signal_engine=signal_engine,
            corporate_action_risk_use_case=corporate_action_risk_use_case,
            ticker_profile_classifier_factory=ticker_profile_classifier_factory,
            institutional_accumulation_config_factory=institutional_accumulation_config_factory,
            sector_context_builder_factory=sector_context_builder_factory,
            sector_macro_context_builder_factory=sector_macro_context_builder_factory,
            company_quality_context_builder_factory=company_quality_context_builder_factory,
            macro_calendar_repository=macro_calendar_repository,
        )
        self._input_collector = PlanSwingInputCollector(
            market_repository=market_repository,
            broker_repository=broker_repository,
            refresh_data=refresh_data,
            build_data_freshness=build_data_freshness,
            build_flow_detail=build_flow_detail,
            build_broker_detail=build_broker_detail,
            build_accumulation_candidate_evaluation=build_accumulation_candidate_evaluation,
            evaluate_market_context=evaluate_market_context,
            signal_evidence_context_builder=signal_evidence_context_builder,
            session_resolver=session_resolver or EffectiveMarketSessionResolver(market_repository),
            live_signal_evidence_context_use_case=live_signal_evidence_context_use_case,
        )
        self._decision_composer = PlanSwingDecisionComposer(
            risk_trade_setup_composer=self._risk_trade_setup_composer,
            signal_engine=signal_engine,
        )
        self._optional_evidence_runner = PlanSwingOptionalEvidenceRunner(
            market_repository=market_repository,
            registry=registry,
            rules_loader=rules_loader,
            evaluate_setup=evaluate_setup,
            build_broker_quality_note=build_broker_quality_note,
            fetch_sentiment=fetch_sentiment,
            evidence_builder=self._evidence_builder,
        )
        self._sizing_service = PlanSwingSizingService(
            registry=registry,
            load_swing_policy_config=load_swing_policy_config,
            resolve_setup_targets=resolve_setup_targets,
        )
        self._response_assembler = PlanSwingResponseAssembler()

    def execute(
        self,
        request: plan_swing_dto.PlanSwingWorkflowRequest,
    ) -> plan_swing_dto.PlanSwingWorkflowResponse:
        state = self._input_collector.collect(request)
        state = self._decision_composer.compose_initial_risk_and_signal(request, state)
        state = self._sizing_service.compute_atr(request, state)
        state = self._optional_evidence_runner.evaluate_setup_and_broker_quality(request, state)
        state = self._sizing_service.compute_entry_sizing(request, state)
        state = self._optional_evidence_runner.run_backtest_and_sentiment(request, state)
        state = self._decision_composer.compose_trade_setup_and_preview(request, state)
        state = self._sizing_service.resolve_targets_and_percent_sizing(request, state)
        state = self._optional_evidence_runner.build_evidence(request, state)
        state = self._decision_composer.recompose_after_evidence(request, state)
        return self._response_assembler.assemble(request, state)
