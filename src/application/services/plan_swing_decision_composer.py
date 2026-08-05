"""Decision composition phase for swing analysis workflow.

Layer: Application

Owns gate context, initial risk assessment, initial signal assessment,
initial TradeSetup composition, and market-context preview. Extracted from
`PlanSwingWorkflowUseCase` to keep the use case as orchestration only.

ADR-067 §3: plan does not judge. This module composes no canonical signal
evidence and runs no swing re-score — the Action shown by `plan swing` is
always the screen verdict carried forward (or, for a ticker screen never
judged, the structure-only TradeSetup composed from the initial risk pass).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.application.dto import plan_swing as plan_swing_dto
from src.application.exceptions import NoProductionSignalEvidenceError
from src.application.services.plan_swing_workflow_state import (
    PlanSwingWorkflowState,
)
from src.application.services.swing_judgment_authority import (
    resolve_authoritative_trade_setup,
)

if TYPE_CHECKING:
    from src.application.services.plan_swing_risk_trade_setup import (
        PlanSwingRiskTradeSetupComposer,
    )
    from src.application.services.signal_engine import SignalEngine


class PlanSwingDecisionComposer:
    """Owns risk/signal/trade-setup composition for the plan surface."""

    def __init__(
        self,
        risk_trade_setup_composer: "PlanSwingRiskTradeSetupComposer",
        signal_engine: "SignalEngine | None",
    ) -> None:
        self._risk_trade_setup_composer = risk_trade_setup_composer
        self._signal_engine = signal_engine

    def compose_initial_risk_and_signal(
        self,
        request: plan_swing_dto.PlanSwingWorkflowRequest,
        state: PlanSwingWorkflowState,
    ) -> PlanSwingWorkflowState:
        gate_ctx = self._risk_trade_setup_composer.build_gate_context(
            ticker=request.ticker,
            snapshot_date=request.today,
            accumulation_candidate=state.accumulation_candidate,
            with_technical_gate=request.with_technical_gate,
        )
        risk_response, risk_warnings = self._risk_trade_setup_composer.assess_initial(
            ticker=request.ticker,
            snapshot_date=request.today,
            with_technical_gate=request.with_technical_gate,
            gate_ctx=gate_ctx,
        )
        state.warnings.extend(risk_warnings)

        signal_assessment = None
        availability = None

        if self._signal_engine is None:
            availability = plan_swing_dto.SignalAssessmentAvailability(
                status=plan_swing_dto.SignalAssessmentStatus.UNAVAILABLE,
                unavailable_reason=plan_swing_dto.SignalAssessmentUnavailableReason.SIGNAL_ENGINE_UNAVAILABLE,
            )
        else:
            try:
                if (
                    state.accumulation_candidate is not None
                    and state.accumulation_candidate.signal_assessment is not None
                ):
                    signal_assessment = state.accumulation_candidate.signal_assessment
                    availability = plan_swing_dto.SignalAssessmentAvailability(
                        status=plan_swing_dto.SignalAssessmentStatus.AVAILABLE,
                    )
                else:
                    availability = plan_swing_dto.SignalAssessmentAvailability(
                        status=plan_swing_dto.SignalAssessmentStatus.UNAVAILABLE,
                        unavailable_reason=plan_swing_dto.SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
                    )
            except (NoProductionSignalEvidenceError, TypeError, ValueError):
                raise
            except Exception as exc:
                state.warnings.append(f"Signal assessment unavailable: {exc}")
                availability = plan_swing_dto.SignalAssessmentAvailability(
                    status=plan_swing_dto.SignalAssessmentStatus.UNAVAILABLE,
                    unavailable_reason=plan_swing_dto.SignalAssessmentUnavailableReason.ASSESSMENT_FAILED,
                )

        state.gate_ctx = gate_ctx
        state.risk_response = risk_response
        state.signal_assessment = signal_assessment
        state.signal_assessment_availability = availability
        return state

    def compose_trade_setup_and_preview(
        self,
        request: plan_swing_dto.PlanSwingWorkflowRequest,
        state: PlanSwingWorkflowState,
    ) -> PlanSwingWorkflowState:
        signal_assessment_to_pass = state.signal_assessment
        if (
            state.signal_assessment_availability is not None
            and state.signal_assessment_availability.status
            == plan_swing_dto.SignalAssessmentStatus.UNAVAILABLE
        ):
            signal_assessment_to_pass = None

        trade_setup, trade_setup_warnings = self._risk_trade_setup_composer.compose_trade_setup(
            ticker=request.ticker,
            snapshot_date=request.today,
            signal_assessment=signal_assessment_to_pass,
            risk_response=state.risk_response,
        )
        state.warnings.extend(trade_setup_warnings)

        (
            market_context_signal_preview,
            market_context_risk_preview,
            market_context_trade_setup_preview,
            mce_preview_warnings,
        ) = self._risk_trade_setup_composer.compose_market_context_preview(
            ticker=request.ticker,
            snapshot_date=request.today,
            market_regime=state.market_regime,
            signal_assessment=signal_assessment_to_pass,
            risk_response=state.risk_response,
        )
        state.warnings.extend(mce_preview_warnings)

        # ADR-054 S3 / ADR-067 §3: Action is screen TradeSetup whenever screen
        # produced one. There is no flag that lets plan override it.
        trade_setup, authority_note = resolve_authoritative_trade_setup(
            state.accumulation_candidate,
            plan_recomputed=trade_setup,
        )
        if authority_note:
            state.warnings.append(authority_note)

        state.trade_setup = trade_setup
        state.market_context_signal_preview = market_context_signal_preview
        state.market_context_risk_preview = market_context_risk_preview
        state.market_context_trade_setup_preview = market_context_trade_setup_preview
        state.verdict = plan_swing_dto.SwingVerdict(
            trade_setup=trade_setup,
            signal_assessment=signal_assessment_to_pass,
            risk_response=state.risk_response,
            market_regime=state.market_regime,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
            signal_assessment_availability=state.signal_assessment_availability,
        )
        return state

    def carry_forward_screen_verdict(
        self,
        state: PlanSwingWorkflowState,
    ) -> PlanSwingWorkflowState:
        """Final Action resolution after the diagnostic evidence pass.

        ADR-067 §3: plan carries the screen verdict forward and computes no
        verdict of its own. No canonical evidence is assembled here and the
        SignalEngine is never re-invoked — the only decision made is *whose*
        already-composed TradeSetup the plan verdict shows.
        """
        trade_setup, authority_note = resolve_authoritative_trade_setup(
            state.accumulation_candidate,
            plan_recomputed=state.trade_setup,
        )
        if authority_note and authority_note not in state.warnings:
            state.warnings.append(authority_note)
        if trade_setup is not state.trade_setup:
            state.trade_setup = trade_setup
            if state.verdict is not None:
                state.verdict = replace(state.verdict, trade_setup=trade_setup)
        return state
