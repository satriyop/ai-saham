"""Exit evaluation engine for swing backtests.

Layer: Application Service
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.swing_backtest import SwingBacktestRequest, SwingBacktestTrade
from src.application.services.backtest_statistics import pct_change_pct
from src.application.services.swing_backtest_position_builder import SwingBacktestOpenPosition
from src.application.use_case.accumulation_screen_use_case import resolve_setup_targets
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository


class SwingBacktestExitEngine:
    """Evaluates trailing stop hits, profit targets, forced closures, and holding days."""

    def __init__(self, market_repository: MarketDataRepository) -> None:
        self._market_repo = market_repository

    def maybe_exit(
        self,
        position: SwingBacktestOpenPosition,
        current_date: date,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade | None:
        """Evaluate if an open position hits stops or targets on current date."""
        if current_date <= position.entry_date:
            return None

        candle = self._candle_on(position.ticker, current_date)
        if candle is None:
            return None

        tp_pct = request.take_profit_pct
        sl_pct = request.stop_loss_pct
        if request.setup_targets:
            tp_pct, sl_pct = resolve_setup_targets(
                position.regime, {"setup_targets": request.setup_targets}
            )

        target = position.entry_price * (Decimal("1") + tp_pct / Decimal("100"))
        stop = position.entry_price * (Decimal("1") - sl_pct / Decimal("100"))
        holding_days = self._holding_days(position.ticker, position.entry_date, current_date)

        stop_hit = candle.low <= stop
        target_hit = candle.high >= target
        if stop_hit and (request.same_day_exit_priority == "stop_first" or not target_hit):
            return self.close_trade(position, current_date, stop, "stop", request)
        if target_hit:
            return self.close_trade(position, current_date, target, "target", request)
        if stop_hit:
            return self.close_trade(position, current_date, stop, "stop", request)
        if holding_days >= request.max_hold_days:
            return self.close_trade(position, current_date, candle.close, "max_hold", request)
        return None

    def force_exit(
        self,
        position: SwingBacktestOpenPosition,
        exit_date: date,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade | None:
        """Force close an open position on the final date."""
        candle = self._candle_on(position.ticker, exit_date)
        if candle is None:
            return None
        return self.close_trade(position, exit_date, candle.close, "period_end", request)

    def close_trade(
        self,
        position: SwingBacktestOpenPosition,
        exit_date: date,
        exit_price: Decimal,
        reason: str,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade:
        """Build a completed trade record calculating final P&L and fees."""
        exit_value = Decimal(position.shares) * exit_price
        exit_cost = exit_value * request.cost_bps / Decimal("10000")
        pnl = exit_value - exit_cost - position.entry_value - position.entry_cost
        gross_return = pct_change_pct(exit_price, position.entry_price)
        net_return = round(float(pnl / position.entry_value * Decimal("100")), 4)
        return SwingBacktestTrade(
            ticker=position.ticker,
            entry_date=position.entry_date,
            exit_date=exit_date,
            entry_price=position.entry_price,
            exit_price=exit_price,
            lots=position.lots,
            shares=position.shares,
            entry_value=position.entry_value,
            exit_value=exit_value,
            gross_return_pct=gross_return,
            net_return_pct=net_return,
            pnl=pnl,
            holding_days=self._holding_days(position.ticker, position.entry_date, exit_date),
            exit_reason=reason,
            accum_score=position.accum_score,
            flow_pct=position.flow_pct,
            vwap_disc_pct=position.vwap_disc_pct,
            rsi=position.rsi,
            regime=position.regime,
            setup_match=position.setup_match,
            setup_failed_reasons=position.setup_failed_reasons,
            setup_gates=position.setup_gates,
            trade_setup_action=position.trade_setup_action,
            signal_score=position.signal_score,
            signal_strength=position.signal_strength,
            signal_entry_quality=position.signal_entry_quality,
            signal_breakdown=position.signal_breakdown,
            risk_status=position.risk_status,
            risk_gate=position.risk_gate,
            risk_confidence=position.risk_confidence,
            market_context=position.market_context,
        )

    def _candle_on(self, ticker: str, target_date: date) -> Candle | None:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=target_date,
            end_date=target_date,
        )
        return candles[0] if candles else None

    def _holding_days(self, ticker: str, entry_date: date, exit_date: date) -> int:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=entry_date + timedelta(days=1),
            end_date=exit_date,
        )
        return len([c for c in candles if entry_date < c.date <= exit_date])
