"""
AssessTradeSetupUseCase — compose signal + risk into a unified TradeSetup verdict.

Pure aggregation: no IO, no providers, no side effects.
Takes already-computed AssessSignalResponse and AssessRiskResponse and
applies the composition rule to produce a TradeSetup.

Composition rule (most severe check first):
  1. Structural gate triggered  → BLOCKED_STRUCTURAL
  2. Execution gate triggered   → BLOCKED_EXECUTION
  3. All gates pass:
       signal ENTER → ENTER
       signal WATCH → WATCH
       signal AVOID → AVOID

Layer: Application
Depends on: Domain value objects only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from src.domain.value_objects.signal_assessment import EntryQuality
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

if TYPE_CHECKING:
    from src.application.use_case.assess_risk_use_case import AssessRiskResponse
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class AssessTradeSetupRequest:
    ticker: str
    snapshot_date: date
    signal_response: "AssessSignalResponse"
    risk_response: "AssessRiskResponse"
    market_context: "MarketContext | None" = None


@dataclass(frozen=True)
class AssessTradeSetupResponse:
    setup: TradeSetup


class AssessTradeSetupUseCase:
    """
    Compose signal + risk assessments into a single TradeSetup verdict.

    Stateless — instantiate once and call execute() for each ticker.
    """

    def execute(self, request: AssessTradeSetupRequest) -> AssessTradeSetupResponse:
        sig = request.signal_response
        risk = request.risk_response
        mc = request.market_context

        action = self._resolve_action(sig, risk)
        blocking = self._blocking_gates(risk)

        regime = mc.regime if mc else None
        multiplier = mc.signal_multiplier if mc else 1.0
        tightening = mc.gate_tightening if mc else False

        raw = sig.signal_score_raw if sig.signal_score_raw is not None else sig.score

        rationale = self._build_rationale(action, sig, risk, mc)

        setup = TradeSetup(
            ticker=request.ticker,
            snapshot_date=request.snapshot_date,
            action=action,
            signal_score=sig.score,
            signal_score_raw=raw,
            signal_strength=sig.assessment.strength,
            blocking_gates=blocking,
            regime=regime,
            signal_multiplier=multiplier,
            gate_tightening=tightening,
            rationale=rationale,
        )
        return AssessTradeSetupResponse(setup=setup)

    # ── internals ─────────────────────────────────────────────────────────────

    def _resolve_action(
        self,
        sig: "AssessSignalResponse",
        risk: "AssessRiskResponse",
    ) -> SetupAction:
        gate = risk.assessment.gate_triggered
        if gate:
            if risk.assessment.gate_is_structural:
                return SetupAction.BLOCKED_STRUCTURAL
            return SetupAction.BLOCKED_EXECUTION

        eq = sig.assessment.entry_quality
        if eq == EntryQuality.ENTER:
            return SetupAction.ENTER
        if eq == EntryQuality.WATCH:
            return SetupAction.WATCH
        return SetupAction.AVOID

    def _blocking_gates(self, risk: "AssessRiskResponse") -> tuple[str, ...]:
        gate = risk.assessment.gate_triggered
        return (gate,) if gate else ()

    def _build_rationale(
        self,
        action: SetupAction,
        sig: "AssessSignalResponse",
        risk: "AssessRiskResponse",
        mc: "MarketContext | None",
    ) -> str:
        parts: list[str] = [f"Signal {sig.score}/100 ({sig.assessment.strength.value})"]

        raw = sig.signal_score_raw
        if raw is not None and raw != sig.score:
            parts[0] += f" [raw {raw}→{sig.score} via regime]"

        if action.is_blocked:
            gate = risk.assessment.gate_triggered or "unknown"
            parts.append(f"Blocked by {gate}")
        else:
            parts.append("gate: open")

        if mc is not None:
            parts.append(f"Regime {mc.regime.value} ×{mc.signal_multiplier:.2f}")
            if mc.gate_tightening:
                parts.append("gate_tightening ON")

        return " | ".join(parts)
