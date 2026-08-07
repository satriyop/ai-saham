"""Response assembly phase for swing analysis workflow.

Layer: Application

Owns diagnostics construction, module flag assembly, and the final
`PlanSwingWorkflowResponse` construction. Extracted from
`PlanSwingWorkflowUseCase` to keep the use case as orchestration only.
"""

from __future__ import annotations

from src.application.dto import plan_swing as plan_swing_dto
from src.application.services.plan_swing_workflow_state import (
    PlanSwingWorkflowState,
)


class PlanSwingResponseAssembler:
    """Builds the final workflow response from accumulated pipeline state."""

    def assemble(
        self,
        request: plan_swing_dto.PlanSwingWorkflowRequest,
        state: PlanSwingWorkflowState,
    ) -> plan_swing_dto.PlanSwingWorkflowResponse:
        verdict = state.verdict
        if verdict is None:
            raise ValueError("state.verdict is missing")
        judgment_ref = state.judgment_ref
        if judgment_ref is None:
            raise ValueError("state.judgment_ref is missing")
        if judgment_ref is not verdict.judgment_ref:
            raise ValueError("state and verdict must share the exact judgment reference")
        evidence = state.evidence
        if evidence is None:
            evidence = plan_swing_dto.SwingEvidence(
                accumulation_candidate=state.accumulation_candidate,
                setup_eval=state.setup_eval,
                backtest_result=state.backtest_result,
                sentiment_response=state.sentiment_response,
                sentiment_warning=state.sentiment_warning,
                take_profit_pct=state.take_profit_pct,
                stop_loss_pct=state.stop_loss_pct,
                regime_label=state.regime_label,
            )
            state.evidence = evidence
        diagnostics = plan_swing_dto.SwingDiagnostics(
            data_freshness=state.data_freshness,
            flow_detail=state.flow_detail,
            broker_detail=state.broker_detail,
            broker_quality_note=state.broker_quality_note,
            refresh_actions=state.refresh_actions,
            warnings=tuple(state.warnings),
        )
        state.diagnostics = diagnostics

        return plan_swing_dto.PlanSwingWorkflowResponse(
            ticker=request.ticker,
            today=request.today,
            refresh_actions=state.refresh_actions,
            data_freshness=state.data_freshness,
            flow_detail=state.flow_detail,
            broker_detail=state.broker_detail,
            candles=state.candles,
            latest_close=state.latest_close,
            accumulation_candidate=state.accumulation_candidate,
            atr_value=state.atr_value,
            sizing=state.sizing,
            setup_eval=state.setup_eval,
            setup_sizing=state.setup_sizing,
            broker_quality_note=state.broker_quality_note,
            backtest_result=state.backtest_result,
            sentiment_response=state.sentiment_response,
            sentiment_warning=state.sentiment_warning,
            take_profit_pct=state.take_profit_pct,
            stop_loss_pct=state.stop_loss_pct,
            regime_label=state.regime_label,
            judgment_ref=judgment_ref,
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
            },
            warnings=tuple(state.warnings),
            effective_session=state.effective_session,
        )
