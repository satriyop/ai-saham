"""
Application workflow coordinator for `saham analyze swing`.

Layer: Application
AI usage: Optional sentiment provider, controlled by injected fetcher.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.ports.rules_loader import RulesLoader

if TYPE_CHECKING:
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
    from src.application.services.ticker_profile_classifier import (
        TickerProfileClassifier,
    )
    from src.application.use_case.assess_corporate_action_event_risk_use_case import (
        AssessCorporateActionEventRiskUseCase,
    )

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.services.swing_analysis_atr import compute_swing_atr
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)
from src.application.services.swing_analysis_risk_trade_setup import (
    SwingAnalysisRiskTradeSetupComposer,
)
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.application.use_case.score_foreign_flow_use_case import ForeignFlowScorePolicy
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.candidate_observations_repository import (
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import RiskGate
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext

class SwingAnalysisWorkflowUseCase:
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
        build_accumulation_candidate: Callable[..., Any | None],
        evaluate_setup: Callable[[Any | None, Any | None], Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        load_swing_config: Callable[[], Any],
        resolve_setup_targets: Callable[[str | None, Any], tuple[Decimal, Decimal]],
        rules_loader: RulesLoader,
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
        signal_engine: "SignalEngine | None" = None,
        risk_engine: "RiskEngine | None" = None,
        candidate_observations_repository: CandidateObservationsRepository | None = None,
        foreign_flow_score_policy: ForeignFlowScorePolicy | None = None,
        corporate_action_risk_use_case: "AssessCorporateActionEventRiskUseCase | None" = None,
        ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier] | None = None,
        institutional_accumulation_config_factory: (
            Callable[[], InstitutionalAccumulationConfig] | None
        ) = None,
        sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder] | None = None,
        company_quality_context_builder_factory: (
            Callable[[], CompanyQualityContextEvidenceBuilder] | None
        ) = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._evaluate_setup = evaluate_setup
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._load_swing_config = load_swing_config
        self._resolve_setup_targets = resolve_setup_targets
        self._rules_loader = rules_loader
        self._evaluate_market_context = evaluate_market_context
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []
        self._signal_engine = signal_engine
        self._risk_engine = risk_engine
        self._candidate_observations_repo = candidate_observations_repository
        self._corporate_action_risk_use_case = corporate_action_risk_use_case
        # Derive weights from the same policy ScoreForeignFlowUseCase/screener
        # use, so the two can never drift apart (see ADR-039).
        self._flow_confirmation_builder = FlowConfirmationEvidenceBuilder(
            foreign_flow_score_policy=foreign_flow_score_policy
        )
        self._risk_trade_setup_composer = SwingAnalysisRiskTradeSetupComposer(
            market_repository=market_repository,
            registry=registry,
            structural_gates=self._structural_gates,
            execution_gates=self._execution_gates,
            signal_engine=signal_engine,
            risk_engine=risk_engine,
        )
        self._evidence_builder = SwingAnalysisEvidenceBuilder(
            market_repository=market_repository,
            broker_repository=broker_repository,
            registry=registry,
            rules_loader=rules_loader,
            flow_confirmation_builder=self._flow_confirmation_builder,
            candidate_observations_repository=candidate_observations_repository,
            signal_engine=signal_engine,
            corporate_action_risk_use_case=corporate_action_risk_use_case,
            ticker_profile_classifier_factory=ticker_profile_classifier_factory,
            institutional_accumulation_config_factory=institutional_accumulation_config_factory,
            sector_context_builder_factory=sector_context_builder_factory,
            company_quality_context_builder_factory=company_quality_context_builder_factory,
        )

    def execute(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
    ) -> swing_analysis_dto.SwingAnalysisWorkflowResponse:
        warnings: list[str] = []

        refresh_actions = ("disabled",)
        if request.auto_refresh:
            refresh_actions = self._refresh_data(
                ticker=request.ticker,
                db_path=request.db_path,
                force_refresh=request.force_refresh,
            )

        data_freshness = self._build_data_freshness(
            ticker=request.ticker,
            as_of_date=request.today,
            market_repo=self._market_repo,
            broker_repo=self._broker_repo,
            refresh_actions=refresh_actions,
        )
        needs_broker_detail = request.include_flow_detail or request.setup_name is not None
        flow_detail = None
        if request.include_flow_detail:
            flow_detail = self._build_flow_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=request.flow_window,
                as_of_date=request.today,
            )
        broker_detail = None
        if needs_broker_detail:
            broker_detail = self._build_broker_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=5,
                as_of_date=request.today,
            )

        candles = self._market_repo.get_candles(request.ticker)
        if not candles:
            raise SwingAnalysisDataUnavailable(request.ticker)
        latest_close = candles[-1].close

        accumulation_candidate = None
        try:
            accumulation_candidate = self._build_accumulation_candidate(
                ticker=request.ticker,
                window=request.window,
            )
        except Exception as exc:
            warnings.append(f"Accumulation unavailable: {exc}")

        market_regime = None
        if request.with_market_context:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=request.today,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        gate_ctx = self._risk_trade_setup_composer.build_gate_context(
            ticker=request.ticker,
            snapshot_date=request.today,
            accumulation_candidate=accumulation_candidate,
            with_technical_gate=request.with_technical_gate,
        )
        risk_response, risk_warnings = self._risk_trade_setup_composer.assess_initial(
            ticker=request.ticker,
            snapshot_date=request.today,
            with_technical_gate=request.with_technical_gate,
            gate_ctx=gate_ctx,
        )
        warnings.extend(risk_warnings)

        signal_assessment = None
        if self._signal_engine is not None:
            try:
                if (
                    accumulation_candidate is not None
                    and accumulation_candidate.signal_assessment is not None
                ):
                    # Fast path: reuse screener's pre-computed raw signal — no recomputation
                    signal_assessment = accumulation_candidate.signal_assessment
                elif accumulation_candidate is not None:
                    # Fallback: candidate exists but screener ran without a signal_engine
                    signal_ctx = build_signal_context_from_candidate(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        candidate=accumulation_candidate,
                        signal_engine=self._signal_engine,
                    )
                    signal_assessment = self._signal_engine.evaluate_with_context(
                        request.ticker,
                        signal_ctx,
                        market_context=market_regime,
                        setup_family=request.setup_name,
                    )
                else:
                    # No candidate — provider-based standalone evaluation
                    signal_assessment = self._signal_engine.evaluate(
                        request.ticker,
                        request.today,
                        market_context=market_regime,
                    )
            except Exception as exc:
                warnings.append(f"Signal assessment unavailable: {exc}")

        atr_value = compute_swing_atr(self._registry, candles)
        sizing: SizingResult | None = None
        setup_eval = None
        setup_sizing: PercentSizingResult | None = None
        if request.setup_name is not None:
            setup_eval = self._evaluate_setup(accumulation_candidate, broker_detail)

        broker_quality_note = self._build_broker_quality_note(
            broker_detail=broker_detail,
            setup_eval=setup_eval,
        )

        setup_entry: Decimal | None = None
        if request.capital is not None and setup_eval is not None and setup_eval.passed:
            setup_entry = (
                Decimal(str(request.entry_price))
                if request.entry_price
                else latest_close
            )
        elif request.capital is not None and atr_value and setup_eval is None:
            try:
                entry = (
                    Decimal(str(request.entry_price))
                    if request.entry_price
                    else latest_close
                )
                sizing = compute_position_size(
                    entry=entry,
                    atr=atr_value,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    atr_multiplier=Decimal(str(request.atr_mult)),
                    reward_risk=Decimal(str(request.rr)),
                )
            except ValueError as exc:
                warnings.append(f"Position sizing unavailable: {exc}")

        backtest_result = None
        if request.strategy_name is not None:
            try:
                loader = StrategyLoader(
                    rules_loader=self._rules_loader, registry=self._registry
                )
                rules_path = loader.resolve(request.strategy_name)
                backtest_use_case = BacktestUseCase(
                    repository=self._market_repo,
                    rules_loader=self._rules_loader,
                    registry=self._registry,
                )
                backtest_response = backtest_use_case.execute(
                    BacktestRequest(
                        ticker=request.ticker,
                        rules_file=rules_path,
                        initial_capital=Decimal("100000000"),
                    )
                )
                backtest_result = backtest_response.result
            except Exception as exc:
                warnings.append(f"Backtest unavailable: {exc}")

        sentiment_response = None
        sentiment_warning = None
        if request.include_sentiment:
            sentiment_response, sentiment_warning = self._fetch_sentiment(
                ticker=request.ticker,
                sentiment_verbose=request.sentiment_verbose,
            )

        trade_setup, trade_setup_warnings = self._risk_trade_setup_composer.compose_trade_setup(
            ticker=request.ticker,
            snapshot_date=request.today,
            signal_assessment=signal_assessment,
            risk_response=risk_response,
        )
        warnings.extend(trade_setup_warnings)

        (
            market_context_signal_preview,
            market_context_risk_preview,
            market_context_trade_setup_preview,
            mce_preview_warnings,
        ) = self._risk_trade_setup_composer.compose_market_context_preview(
            ticker=request.ticker,
            snapshot_date=request.today,
            market_regime=market_regime,
            signal_assessment=signal_assessment,
            risk_response=risk_response,
        )
        warnings.extend(mce_preview_warnings)

        swing_config = self._load_swing_config()
        regime_label = market_regime.regime.value if market_regime else None
        take_profit_pct, stop_loss_pct = self._resolve_setup_targets(
            regime_label,
            swing_config,
        )
        if setup_entry is not None and request.capital is not None:
            try:
                setup_sizing = compute_percent_position_size(
                    entry=setup_entry,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                )
            except ValueError as exc:
                warnings.append(f"Setup sizing unavailable: {exc}")

        verdict = swing_analysis_dto.SwingVerdict(
            trade_setup=trade_setup,
            signal_assessment=signal_assessment,
            risk_response=risk_response,
            market_regime=market_regime,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
        )
        evidence_build = self._evidence_builder.build(
            ticker=request.ticker,
            snapshot_date=request.today,
            benchmark=request.benchmark,
            candles=candles,
            accumulation_candidate=accumulation_candidate,
            setup_eval=setup_eval,
            setup_name=request.setup_name,
            strategy_name=request.strategy_name,
            swing_config=swing_config,
        )
        warnings.extend(evidence_build.warnings)
        setup_evidence = evidence_build.setup_evidence
        flow_confirmation_evidence = evidence_build.flow_confirmation_evidence
        setup_phase = evidence_build.setup_phase
        strategy_rule_evidence = evidence_build.strategy_rule_evidence
        institutional_accumulation_evidence = evidence_build.institutional_accumulation_evidence
        ticker_profile_snapshot = evidence_build.ticker_profile_snapshot
        sector_context_evidence = evidence_build.sector_context_evidence
        company_quality_context_evidence = evidence_build.company_quality_context_evidence
        corporate_action_risk = evidence_build.corporate_action_risk

        evidence = swing_analysis_dto.SwingEvidence(
            accumulation_candidate=accumulation_candidate,
            setup_eval=setup_eval,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
            setup_evidence=setup_evidence,
            flow_confirmation_evidence=flow_confirmation_evidence,
            setup_phase=setup_phase,
            strategy_rule_evidence=strategy_rule_evidence,
            institutional_accumulation_evidence=institutional_accumulation_evidence,
            ticker_profile_snapshot=ticker_profile_snapshot,
            sector_context_evidence=sector_context_evidence,
            company_quality_context_evidence=company_quality_context_evidence,
            corporate_action_risk=corporate_action_risk,
        )

        # Re-score with evidence now that both groups are available. Signal was
        # computed earlier (before setup_eval existed), so that score had no
        # evidence groups and confidence=0. Recompose all downstream outputs
        # (TradeSetup, MCE preview) so verdict is internally consistent.
        if (
            self._signal_engine is not None
            and accumulation_candidate is not None
            and (setup_evidence is not None or flow_confirmation_evidence is not None)
        ):
            try:
                _evidence_ctx = build_signal_context_from_candidate(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    candidate=accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
                signal_assessment = self._signal_engine.evaluate_with_context(
                    request.ticker,
                    _evidence_ctx,
                    market_context=market_regime,
                    setup_evidence=setup_evidence,
                    flow_confirmation_evidence=flow_confirmation_evidence,
                    setup_family=request.setup_name,
                    setup_phase=setup_phase,
                    sector_context_evidence=sector_context_evidence,
                    company_quality_context_evidence=company_quality_context_evidence,
                )
            except Exception as exc:
                warnings.append(f"Evidence-enriched signal re-score unavailable: {exc}")
            else:
                # Re-score succeeded — recompose trade_setup and MCE preview so
                # all three fields in verdict use the same enriched signal score.
                (
                    _new_trade_setup,
                    _new_mce_signal,
                    _new_mce_trade_preview,
                    recompose_warnings,
                ) = self._risk_trade_setup_composer.recompose_after_signal_rescore(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    signal_assessment=signal_assessment,
                    risk_response=risk_response,
                    market_context_risk_preview=market_context_risk_preview,
                    market_regime=market_regime,
                    fallback_trade_setup=trade_setup,
                    fallback_market_context_signal_preview=market_context_signal_preview,
                    fallback_market_context_trade_setup_preview=market_context_trade_setup_preview,
                )
                warnings.extend(recompose_warnings)

                verdict = replace(
                    verdict,
                    signal_assessment=signal_assessment,
                    trade_setup=_new_trade_setup,
                    market_context_signal_preview=_new_mce_signal,
                    market_context_trade_setup_preview=_new_mce_trade_preview,
                )

        diagnostics = swing_analysis_dto.SwingDiagnostics(
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            broker_quality_note=broker_quality_note,
            refresh_actions=refresh_actions,
            warnings=tuple(warnings),
        )

        return swing_analysis_dto.SwingAnalysisWorkflowResponse(
            ticker=request.ticker,
            today=request.today,
            refresh_actions=refresh_actions,
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            candles=candles,
            latest_close=latest_close,
            accumulation_candidate=accumulation_candidate,
            risk_response=risk_response,
            atr_value=atr_value,
            sizing=sizing,
            setup_eval=setup_eval,
            setup_sizing=setup_sizing,
            broker_quality_note=broker_quality_note,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            market_regime=market_regime,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
            signal_assessment=verdict.signal_assessment,
            trade_setup=verdict.trade_setup,
            market_context_signal_preview=verdict.market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=verdict.market_context_trade_setup_preview,
            verdict=verdict,
            evidence=evidence,
            diagnostics=diagnostics,
            modules={
                "setup": request.setup_name is not None,
                "sizing": request.capital is not None,
                "strategy": request.strategy_name is not None,
                "sentiment": request.include_sentiment,
                "flow_detail": request.include_flow_detail,
                "signal_detail": request.include_signal_detail,
                "risk_detail": request.include_risk_detail,
                "market_detail": request.include_market_detail,
                "market_context": request.with_market_context,
                "technical_gate": request.with_technical_gate,
            },
            warnings=tuple(warnings),
        )

class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker
