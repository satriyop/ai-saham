"""Position builder and sizing service for swing backtests.

Layer: Application Service
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.swing_backtest import SwingBacktestRequest
from src.application.services.swing_backtest_trade_setup_attributor import (
    SwingBacktestTradeSetupAttributor,
)
from src.domain.value_objects.idx_market import SHARES_PER_LOT
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate


@dataclass
class SwingBacktestOpenPosition:
    """An open swing position tracked within backtest simulation."""

    ticker: str
    entry_date: date
    entry_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    entry_cost: Decimal
    foreign_flow_score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None
    setup_match: str | None
    setup_failed_reasons: tuple[str, ...]
    setup_gates: tuple[SetupGate, ...]
    trade_setup_action: str | None
    signal_score: int | None
    signal_strength: str | None
    signal_entry_quality: str | None
    signal_breakdown: tuple[tuple[str, float], ...]
    risk_status: str | None
    risk_gate: str | None
    risk_confidence: int | None
    market_context: MarketContext | None


# Compatibility alias
_OpenPosition = SwingBacktestOpenPosition


class SwingBacktestPositionBuilder:
    """Manages SwingBacktestOpenPosition instantiation, risk-pct calculations, and lot sizing."""

    def __init__(self, trade_setup_attributor: SwingBacktestTradeSetupAttributor) -> None:
        self._attributor = trade_setup_attributor

    def build(
        self,
        candidate: AccumulationCandidate,
        setup_evaluation: SetupEvaluation,
        signal_date: date,
        cash: Decimal,
        request: SwingBacktestRequest,
        market_context: MarketContext | None,
    ) -> SwingBacktestOpenPosition | None:
        """Calculate sized position size and return SwingBacktestOpenPosition if affordable."""
        entry = candidate.current_price
        if entry <= 0:
            return None

        stop_distance = entry * request.stop_loss_pct / Decimal("100")
        if stop_distance <= 0:
            return None

        risk_amount = request.capital * request.risk_pct
        shares_by_risk = int(risk_amount / stop_distance)
        cost_multiplier = Decimal("1") + request.cost_bps / Decimal("10000")
        max_affordable_shares = int(cash / (entry * cost_multiplier))
        shares = min(shares_by_risk, max_affordable_shares)
        lots = shares // SHARES_PER_LOT
        shares = lots * SHARES_PER_LOT
        if lots <= 0:
            return None

        entry_value = Decimal(shares) * entry
        entry_cost = entry_value * request.cost_bps / Decimal("10000")

        signal = candidate.signal_assessment.assessment if candidate.signal_assessment else None
        risk_response, trade_setup = self._attributor.assess(
            candidate=candidate,
            signal_date=signal_date,
            market_context=market_context,
        )
        risk = risk_response.assessment if risk_response is not None else None

        return SwingBacktestOpenPosition(
            ticker=candidate.ticker,
            entry_date=signal_date,
            entry_price=entry,
            lots=lots,
            shares=shares,
            entry_value=entry_value,
            entry_cost=entry_cost,
            foreign_flow_score=candidate.foreign_flow_score,
            flow_pct=candidate.avg_flow_ratio,
            vwap_disc_pct=candidate.vwap_discount_pct,
            rsi=candidate.rsi,
            regime=market_context.regime.value if market_context is not None else None,
            setup_match=getattr(setup_evaluation.match, "value", str(setup_evaluation.match)),
            setup_failed_reasons=tuple(setup_evaluation.failed_reasons),
            setup_gates=setup_evaluation.gates,
            trade_setup_action=trade_setup.action.value if trade_setup is not None else None,
            signal_score=signal.score if signal is not None else None,
            signal_strength=signal.strength.value if signal is not None else None,
            signal_entry_quality=signal.entry_quality.value if signal is not None else None,
            signal_breakdown=signal.breakdown if signal is not None else (),
            risk_status=risk.risk_level_name if risk is not None else None,
            risk_gate=risk.gate_triggered if risk is not None else None,
            risk_confidence=risk.confidence if risk is not None else None,
            market_context=market_context,
        )
