"""Response assembly phase for swing analysis workflow.

Layer: Application

Owns diagnostics construction, module flag assembly, and the final
`SwingAnalysisWorkflowResponse` construction. Extracted from
`SwingAnalysisWorkflowUseCase` to keep the use case as orchestration only.
"""
from __future__ import annotations

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)


class SwingAnalysisResponseAssembler:
    """Builds the final workflow response from accumulated pipeline state."""

    def assemble(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> swing_analysis_dto.SwingAnalysisWorkflowResponse:
        verdict = state.verdict
        if verdict is None:
            raise ValueError("state.verdict is missing")
        if state.signal_assessment_availability is None:
            raise ValueError("state.signal_assessment_availability is missing")
        if (
            state.signal_assessment_availability
            != verdict.signal_assessment_availability
        ):
            raise ValueError(
                "state and verdict signal assessment availability differ"
            )
        diagnostics = swing_analysis_dto.SwingDiagnostics(
            data_freshness=state.data_freshness,
            flow_detail=state.flow_detail,
            broker_detail=state.broker_detail,
            broker_quality_note=state.broker_quality_note,
            refresh_actions=state.refresh_actions,
            warnings=tuple(state.warnings),
        )
        state.diagnostics = diagnostics

        return swing_analysis_dto.SwingAnalysisWorkflowResponse(
            ticker=request.ticker,
            today=request.today,
            refresh_actions=state.refresh_actions,
            data_freshness=state.data_freshness,
            flow_detail=state.flow_detail,
            broker_detail=state.broker_detail,
            candles=state.candles,
            latest_close=state.latest_close,
            accumulation_candidate=state.accumulation_candidate,
            risk_response=state.risk_response,
            atr_value=state.atr_value,
            sizing=state.sizing,
            setup_eval=state.setup_eval,
            setup_sizing=state.setup_sizing,
            broker_quality_note=state.broker_quality_note,
            backtest_result=state.backtest_result,
            sentiment_response=state.sentiment_response,
            sentiment_warning=state.sentiment_warning,
            market_regime=state.market_regime,
            take_profit_pct=state.take_profit_pct,
            stop_loss_pct=state.stop_loss_pct,
            regime_label=state.regime_label,
            signal_assessment=verdict.signal_assessment,
            trade_setup=verdict.trade_setup,
            market_context_signal_preview=verdict.market_context_signal_preview,
            market_context_risk_preview=state.market_context_risk_preview,
            market_context_trade_setup_preview=verdict.market_context_trade_setup_preview,
            verdict=verdict,
            evidence=state.evidence,
            diagnostics=diagnostics,
            signal_assessment_availability=verdict.signal_assessment_availability,
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
            warnings=tuple(state.warnings),
            effective_session=state.effective_session,
        )
