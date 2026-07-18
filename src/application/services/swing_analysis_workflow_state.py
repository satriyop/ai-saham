"""Mutable intermediate state for the swing analysis workflow pipeline.

Layer: Application

Carries values produced by one workflow collaborator and consumed by a
later one. Extracted from `SwingAnalysisWorkflowUseCase` to keep the use
case as orchestration only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.application.dto.accumulation_screen import (
        AccumulationCandidate,
        AccumulationCandidateEvaluationResult,
    )
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.dto.built_evidence import BuiltFlowEvidence, BuiltSetupEvidence
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.application.dto.swing_analysis import (
        SignalAssessmentAvailability,
        SwingDiagnostics,
        SwingEvidence,
        SwingVerdict,
    )
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.services.position_sizer import PercentSizingResult, SizingResult
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )
    from src.domain.rules.risk_gate import GateContext
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.trade_setup import TradeSetup


@dataclass
class SwingAnalysisWorkflowState:
    """Intermediate values threaded through the swing analysis pipeline."""

    warnings: list[str] = field(default_factory=list)
    refresh_actions: tuple[str, ...] = ("disabled",)
    data_freshness: Any = None
    flow_detail: Any = None
    broker_detail: Any = None
    candles: list[Any] = field(default_factory=list)
    latest_close: Decimal | None = None
    # Sole source of truth for the accumulation candidate (ADR-041
    # CANONICAL-EVIDENCE-BOUNDARY) — never a separate mutable field, which
    # could disagree with this. Access the candidate via the
    # `accumulation_candidate` property below.
    accumulation_evaluation: "AccumulationCandidateEvaluationResult | None" = None
    signal_evidence_execution_context: "SignalEvidenceExecutionContext | None" = None
    market_regime: "MarketContext | None" = None
    gate_ctx: "GateContext | None" = None
    risk_response: Any | None = None
    signal_assessment: "AssessSignalResponse | None" = None
    signal_assessment_availability: "SignalAssessmentAvailability | None" = None
    atr_value: Decimal | None = None
    setup_eval: Any | None = None
    broker_quality_note: Any | None = None
    setup_entry: Decimal | None = None
    sizing: "SizingResult | None" = None
    setup_sizing: "PercentSizingResult | None" = None
    backtest_result: Any | None = None
    sentiment_response: Any | None = None
    sentiment_warning: str | None = None
    trade_setup: "TradeSetup | None" = None
    market_context_signal_preview: "AssessSignalResponse | None" = None
    market_context_risk_preview: Any | None = None
    market_context_trade_setup_preview: "TradeSetup | None" = None
    swing_config: Any = None
    regime_label: str | None = None
    take_profit_pct: Decimal | None = None
    stop_loss_pct: Decimal | None = None
    verdict: "SwingVerdict | None" = None
    evidence: "SwingEvidence | None" = None
    diagnostics: "SwingDiagnostics | None" = None
    # Complete built evidence (evidence + exact consumed-row provenance,
    # ADR-041 CANONICAL-EVIDENCE-BOUNDARY) — the canonical pre-score input
    # source. `evidence` above carries only the unwrapped presentation
    # values for diagnostic rendering; these are never unwrapped until
    # SetupEvidenceGroupInput/FlowEvidenceGroupInput are constructed.
    built_setup_evidence: "BuiltSetupEvidence | None" = None
    built_flow_evidence: "BuiltFlowEvidence | None" = None

    @property
    def accumulation_candidate(self) -> "AccumulationCandidate | None":
        return (
            self.accumulation_evaluation.candidate
            if self.accumulation_evaluation is not None
            else None
        )

    @property
    def effective_session(self) -> "EffectiveMarketSession | None":
        context = self.signal_evidence_execution_context
        return context.effective_session if context is not None else None

    @property
    def source_availability_use_case(self) -> "AssessSourceAvailabilityUseCase | None":
        context = self.signal_evidence_execution_context
        return context.source_availability_use_case if context is not None else None
