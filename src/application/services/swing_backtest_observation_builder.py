"""Candidate observation builder for swing backtests.

Layer: Application Service
"""

from datetime import date, timedelta

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.swing_backtest import (
    SwingBacktestCandidateObservation,
    SwingBacktestRequest,
)
from src.application.services.backtest_statistics import pct_change_pct
from src.application.services.swing_backtest_trade_setup_attributor import (
    SwingBacktestTradeSetupAttributor,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.setup_evaluation import SetupEvaluation


class SwingBacktestObservationBuilder:
    """Builds candidate observation records containing setup evaluation and forward returns."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        trade_setup_attributor: SwingBacktestTradeSetupAttributor,
    ) -> None:
        self._market_repo = market_repository
        self._attributor = trade_setup_attributor

    def build(
        self,
        candidate: AccumulationCandidate,
        setup_evaluation: SetupEvaluation,
        signal_date: date,
        request: SwingBacktestRequest,
        market_context: MarketContext | None,
    ) -> SwingBacktestCandidateObservation | None:
        entry = candidate.current_price
        if entry <= 0:
            return None

        forward_candle = self._observation_exit_candle(candidate.ticker, signal_date, request)
        if forward_candle is None:
            return None

        signal = candidate.signal_assessment.assessment if candidate.signal_assessment else None
        risk_response, trade_setup = self._attributor.assess(
            candidate=candidate,
            signal_date=signal_date,
            market_context=market_context,
        )
        risk = risk_response.assessment if risk_response is not None else None

        return SwingBacktestCandidateObservation(
            ticker=candidate.ticker,
            signal_date=signal_date,
            entry_price=entry,
            observation_exit_date=forward_candle.date,
            observation_exit_price=forward_candle.close,
            forward_return_pct=pct_change_pct(forward_candle.close, entry),
            setup_match=getattr(setup_evaluation.match, "value", str(setup_evaluation.match)),
            setup_failed_reasons=tuple(setup_evaluation.failed_reasons),
            setup_gates=setup_evaluation.gates,
            trade_setup_action=trade_setup.action.value if trade_setup is not None else None,
            signal_score=signal.score if signal is not None else None,
            signal_strength=signal.strength.value if signal is not None else None,
            signal_breakdown=signal.breakdown if signal is not None else (),
            risk_status=risk.risk_level_name if risk is not None else None,
            risk_gate=risk.gate_triggered if risk is not None else None,
            regime=market_context.regime.value if market_context is not None else None,
        )

    def _observation_exit_candle(
        self,
        ticker: str,
        signal_date: date,
        request: SwingBacktestRequest,
    ) -> Candle | None:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(days=request.forward_data_lookahead_days),
        )
        forward_candles = [c for c in candles if c.date > signal_date]
        if not forward_candles:
            return None
        index = min(request.max_hold_days, len(forward_candles)) - 1
        return forward_candles[index]
