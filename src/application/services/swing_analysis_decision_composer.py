"""Decision composition phase for swing analysis workflow.

Layer: Application

Owns gate context, initial risk assessment, initial signal assessment,
initial TradeSetup composition, market-context preview, and the
evidence-enriched signal re-score with recomposition. Extracted from
`SwingAnalysisWorkflowUseCase` to keep the use case as orchestration only.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.domain.value_objects.evidence_source_availability import AvailabilityEnforcementMode

if TYPE_CHECKING:
    from src.application.services.signal_engine import SignalEngine
    from src.application.services.swing_analysis_risk_trade_setup import (
        SwingAnalysisRiskTradeSetupComposer,
    )


class SwingAnalysisDecisionComposer:
    """Owns risk/signal/trade-setup decisions and evidence-enriched re-score."""

    def __init__(
        self,
        risk_trade_setup_composer: "SwingAnalysisRiskTradeSetupComposer",
        signal_engine: "SignalEngine | None",
    ) -> None:
        self._risk_trade_setup_composer = risk_trade_setup_composer
        self._signal_engine = signal_engine

    def compose_initial_risk_and_signal(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
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
        if self._signal_engine is not None:
            try:
                if (
                    state.accumulation_candidate is not None
                    and state.accumulation_candidate.signal_assessment is not None
                ):
                    # Fast path: reuse screener's pre-computed raw signal — no recomputation
                    signal_assessment = state.accumulation_candidate.signal_assessment
                elif state.accumulation_candidate is not None:
                    # Fallback: candidate exists but screener ran without a signal_engine
                    signal_ctx = build_signal_context_from_candidate(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        candidate=state.accumulation_candidate,
                        signal_engine=self._signal_engine,
                    )
                    signal_assessment = self._signal_engine.evaluate_with_context(
                        request.ticker,
                        signal_ctx,
                        market_context=state.market_regime,
                        setup_family=request.setup_name,
                    )
                else:
                    # No candidate — provider-based standalone evaluation
                    signal_assessment = self._signal_engine.evaluate(
                        request.ticker,
                        request.today,
                        market_context=state.market_regime,
                    )
            except Exception as exc:
                state.warnings.append(f"Signal assessment unavailable: {exc}")

        state.gate_ctx = gate_ctx
        state.risk_response = risk_response
        state.signal_assessment = signal_assessment
        return state

    def compose_trade_setup_and_preview(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        trade_setup, trade_setup_warnings = self._risk_trade_setup_composer.compose_trade_setup(
            ticker=request.ticker,
            snapshot_date=request.today,
            signal_assessment=state.signal_assessment,
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
            signal_assessment=state.signal_assessment,
            risk_response=state.risk_response,
        )
        state.warnings.extend(mce_preview_warnings)

        state.trade_setup = trade_setup
        state.market_context_signal_preview = market_context_signal_preview
        state.market_context_risk_preview = market_context_risk_preview
        state.market_context_trade_setup_preview = market_context_trade_setup_preview
        state.verdict = swing_analysis_dto.SwingVerdict(
            trade_setup=trade_setup,
            signal_assessment=state.signal_assessment,
            risk_response=state.risk_response,
            market_regime=state.market_regime,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
        )
        return state

    def recompose_after_evidence(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        evidence = state.evidence
        setup_evidence = evidence.setup_evidence if evidence is not None else None
        flow_confirmation_evidence = (
            evidence.flow_confirmation_evidence if evidence is not None else None
        )

        # Re-score with evidence now that both groups are available. Signal was
        # computed earlier (before setup_eval existed), so that score had no
        # evidence groups and confidence=0. Recompose all downstream outputs
        # (TradeSetup, MCE preview) so verdict is internally consistent.
        if (
            self._signal_engine is not None
            and state.accumulation_candidate is not None
            and (setup_evidence is not None or flow_confirmation_evidence is not None)
        ):
            signal_assessment = state.signal_assessment
            try:
                _evidence_ctx = build_signal_context_from_candidate(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    candidate=state.accumulation_candidate,
                    signal_engine=self._signal_engine,
                )
                signal_assessment = self._signal_engine.evaluate_with_context(
                    request.ticker,
                    _evidence_ctx,
                    market_context=state.market_regime,
                    setup_evidence=setup_evidence,
                    flow_confirmation_evidence=flow_confirmation_evidence,
                    setup_family=request.setup_name,
                    setup_phase=evidence.setup_phase if evidence is not None else None,
                    sector_context_evidence=(
                        evidence.sector_context_evidence if evidence is not None else None
                    ),
                    company_quality_context_evidence=(
                        evidence.company_quality_context_evidence
                        if evidence is not None else None
                    ),
                )
            except Exception as exc:
                state.warnings.append(f"Evidence-enriched signal re-score unavailable: {exc}")
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
                    risk_response=state.risk_response,
                    market_context_risk_preview=state.market_context_risk_preview,
                    market_regime=state.market_regime,
                    fallback_trade_setup=state.trade_setup,
                    fallback_market_context_signal_preview=state.market_context_signal_preview,
                    fallback_market_context_trade_setup_preview=(
                        state.market_context_trade_setup_preview
                    ),
                )
                state.warnings.extend(recompose_warnings)

                state.signal_assessment = signal_assessment
                state.verdict = replace(
                    state.verdict,
                    signal_assessment=signal_assessment,
                    trade_setup=_new_trade_setup,
                    market_context_signal_preview=_new_mce_signal,
                    market_context_trade_setup_preview=_new_mce_trade_preview,
                )

        # DQ-002 Blocker 2 (shadow mode): assemble availability only for
        # evidence groups that were actually produced this run — availability
        # must describe evidence that exists, not evidence a candidate could
        # theoretically have produced. `setup_evidence`/
        # `flow_confirmation_evidence` above already carry that presence
        # check; reuse it here rather than gating on `accumulation_candidate`
        # alone (which exists even when, say, no setup was requested).
        if state.source_availability_use_case is not None:
            assembler = EvidenceSourceAvailabilityAssembler(state.source_availability_use_case)
            if setup_evidence is not None:
                try:
                    state.setup_source_availability = assembler.assess_setup(
                        effective_session=state.effective_session, candles=state.candles
                    )
                except Exception as exc:
                    state.warnings.append(f"Setup source availability unavailable: {exc}")
            if flow_confirmation_evidence is not None:
                try:
                    state.flow_source_availability = assembler.assess_flow(
                        effective_session=state.effective_session,
                        candidate=state.accumulation_candidate,
                    )
                except Exception as exc:
                    state.warnings.append(f"Flow source availability unavailable: {exc}")

        # Attach observational source-availability diagnostics to the
        # canonical signal assessment response. Purely additive — never
        # changes score, coverage, entry_quality, or trade_setup, since it is
        # copied onto whichever signal_assessment already resulted from the
        # logic above (rescored or not).
        if (
            state.signal_assessment is not None
            and (
                state.setup_source_availability is not None
                or state.flow_source_availability is not None
            )
        ):
            state.signal_assessment = replace(
                state.signal_assessment,
                setup_source_availability=state.setup_source_availability,
                flow_source_availability=state.flow_source_availability,
                availability_enforcement=AvailabilityEnforcementMode.SHADOW,
            )
            state.verdict = replace(
                state.verdict, signal_assessment=state.signal_assessment
            )
        return state
