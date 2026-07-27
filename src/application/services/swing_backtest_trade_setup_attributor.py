"""Trade setup and risk assessment attributor service.

Layer: Application Service
"""

import logging
from datetime import date
from typing import Any

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.use_case.assess_trade_setup_use_case import (
    AssessTradeSetupRequest,
    AssessTradeSetupUseCase,
)
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)


class SwingBacktestTradeSetupAttributor:
    """Service for assessing trade setups and evaluating risk gates."""

    def __init__(self, risk_engine: Any = None) -> None:
        self._risk_engine = risk_engine

    def assess(
        self,
        candidate: AccumulationCandidate,
        signal_date: date,
        market_context: MarketContext | None,
    ) -> tuple[Any, Any]:
        """Assess trade setup and evaluate risk gates for a candidate."""
        if self._risk_engine is None or candidate.signal_assessment is None:
            return None, None

        try:
            risk_response = self._risk_engine.assess_with_context(
                candidate.ticker,
                self._build_gate_context(candidate, signal_date),
                market_context=market_context,
            )
        except Exception as exc:
            logger.debug(
                "Swing backtest risk attribution failed for %s on %s: %s",
                candidate.ticker,
                signal_date,
                exc,
            )
            return None, None

        trade_setup = (
            AssessTradeSetupUseCase()
            .execute(
                AssessTradeSetupRequest(
                    ticker=candidate.ticker,
                    snapshot_date=signal_date,
                    signal_response=candidate.signal_assessment,
                    risk_response=risk_response,
                    market_context=market_context,
                )
            )
            .setup
        )
        return risk_response, trade_setup

    @staticmethod
    def _build_gate_context(
        candidate: AccumulationCandidate,
        signal_date: date,
    ) -> GateContext:
        return GateContext(
            ticker=candidate.ticker,
            snapshot_date=signal_date,
            piotroski_f_score=(
                candidate.fundamentals.piotroski_f_score if candidate.fundamentals else None
            ),
            market_cap_idr=(
                candidate.fundamentals.market_cap_idr if candidate.fundamentals else None
            ),
            free_float_pct=(
                candidate.shareholding.free_float_pct
                if candidate.shareholding is not None
                else None
            ),
            five_day_accdist=(
                candidate.bandar_detector.five_day_accdist if candidate.bandar_detector else None
            ),
        )
