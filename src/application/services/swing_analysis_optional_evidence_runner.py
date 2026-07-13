"""Optional evidence phase for swing analysis workflow.

Layer: Application

Owns setup evaluation, broker quality note, strategy backtest, sentiment
fetch, and the evidence builder call (including `SwingEvidence`
construction). Each section is independent and best-effort: a failure
appends a warning and does not abort the workflow. Signal re-scoring is
not performed here — that belongs to the decision composer, which runs
after evidence exists. Extracted from `SwingAnalysisWorkflowUseCase` to
keep the use case as orchestration only.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.services.strategy_loader import StrategyLoader
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase

if TYPE_CHECKING:
    from src.application.ports.rules_loader import RulesLoader
    from src.application.services.swing_analysis_evidence_builder import (
        SwingAnalysisEvidenceBuilder,
    )
    from src.domain.ports.market_data_repository import MarketDataRepository


class SwingAnalysisOptionalEvidenceRunner:
    """Owns best-effort evidence assembly for swing analysis."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        registry: Any,
        rules_loader: "RulesLoader",
        evaluate_setup: Callable[[Any | None, Any | None], Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        evidence_builder: "SwingAnalysisEvidenceBuilder",
    ) -> None:
        self._market_repo = market_repository
        self._registry = registry
        self._rules_loader = rules_loader
        self._evaluate_setup = evaluate_setup
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._evidence_builder = evidence_builder

    def evaluate_setup_and_broker_quality(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        setup_eval = None
        if request.setup_name is not None:
            setup_eval = self._evaluate_setup(state.accumulation_candidate, state.broker_detail)

        broker_quality_note = self._build_broker_quality_note(
            broker_detail=state.broker_detail,
            setup_eval=setup_eval,
        )

        state.setup_eval = setup_eval
        state.broker_quality_note = broker_quality_note
        return state

    def run_backtest_and_sentiment(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
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
                state.warnings.append(f"Backtest unavailable: {exc}")

        sentiment_response = None
        sentiment_warning = None
        if request.include_sentiment:
            sentiment_response, sentiment_warning = self._fetch_sentiment(
                ticker=request.ticker,
                sentiment_verbose=request.sentiment_verbose,
            )

        state.backtest_result = backtest_result
        state.sentiment_response = sentiment_response
        state.sentiment_warning = sentiment_warning
        return state

    def build_evidence(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        evidence_build = self._evidence_builder.build(
            ticker=request.ticker,
            snapshot_date=request.today,
            benchmark=request.benchmark,
            candles=state.candles,
            accumulation_candidate=state.accumulation_candidate,
            setup_eval=state.setup_eval,
            setup_name=request.setup_name,
            strategy_name=request.strategy_name,
            swing_config=state.swing_config,
        )
        state.warnings.extend(evidence_build.warnings)

        state.evidence = swing_analysis_dto.SwingEvidence(
            accumulation_candidate=state.accumulation_candidate,
            setup_eval=state.setup_eval,
            backtest_result=state.backtest_result,
            sentiment_response=state.sentiment_response,
            sentiment_warning=state.sentiment_warning,
            take_profit_pct=state.take_profit_pct,
            stop_loss_pct=state.stop_loss_pct,
            regime_label=state.regime_label,
            setup_evidence=evidence_build.setup_evidence,
            flow_confirmation_evidence=evidence_build.flow_confirmation_evidence,
            setup_phase=evidence_build.setup_phase,
            strategy_rule_evidence=evidence_build.strategy_rule_evidence,
            institutional_accumulation_evidence=(
                evidence_build.institutional_accumulation_evidence
            ),
            ticker_profile_snapshot=evidence_build.ticker_profile_snapshot,
            sector_context_evidence=evidence_build.sector_context_evidence,
            company_quality_context_evidence=evidence_build.company_quality_context_evidence,
            corporate_action_risk=evidence_build.corporate_action_risk,
        )
        return state
