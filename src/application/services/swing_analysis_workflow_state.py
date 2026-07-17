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
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.dto.swing_analysis import SwingDiagnostics, SwingEvidence, SwingVerdict
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.services.position_sizer import PercentSizingResult, SizingResult
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )
    from src.domain.rules.risk_gate import GateContext
    from src.domain.value_objects.evidence_source_availability import (
        EvidenceSourceAvailability,
    )
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
    accumulation_candidate: Any | None = None
    effective_session: "EffectiveMarketSession | None" = None
    market_regime: "MarketContext | None" = None
    # One AssessSourceAvailabilityUseCase per workflow execution (DQ-002
    # Blocker 2), reused for both evidence-group assessments below. Actual
    # assessment happens in SwingAnalysisDecisionComposer.recompose_after_
    # evidence, gated on the corresponding evidence actually existing.
    source_availability_use_case: "AssessSourceAvailabilityUseCase | None" = None
    setup_source_availability: "EvidenceSourceAvailability | None" = None
    flow_source_availability: "EvidenceSourceAvailability | None" = None
    gate_ctx: "GateContext | None" = None
    risk_response: Any | None = None
    signal_assessment: "AssessSignalResponse | None" = None
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
