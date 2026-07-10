"""Portfolio loop coordinator for swing backtests.

Layer: Application Service
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.swing_backtest import (
    SwingBacktestCandidateObservation,
    SwingBacktestDailyEquity,
    SwingBacktestEntrySignal,
    SwingBacktestRequest,
    SwingBacktestTrade,
)
from src.application.services.swing_backtest_exit_engine import SwingBacktestExitEngine
from src.application.services.swing_backtest_position_builder import (
    SwingBacktestOpenPosition,
    SwingBacktestPositionBuilder,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class SwingBacktestSimulationResult:
    """Consolidated simulation execution results."""

    final_equity: Decimal
    trades: list[SwingBacktestTrade]
    candidate_observations: list[SwingBacktestCandidateObservation]
    equity_curve: list[SwingBacktestDailyEquity]
    skipped_no_cash: int
    skipped_duplicate: int
    skipped_no_forward_data: int
    skipped_by_regime: int
    exposure_days: int


class SwingBacktestSimulator:
    """Coordinates daily entries and exits using position and exit engines."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        position_builder: SwingBacktestPositionBuilder,
        exit_engine: SwingBacktestExitEngine,
    ) -> None:
        self._market_repo = market_repository
        self._position_builder = position_builder
        self._exit_engine = exit_engine

    def run(
        self,
        replay_dates: list[date],
        request: SwingBacktestRequest,
        signals_by_date: dict[date, list[SwingBacktestEntrySignal]],
        regime_by_date: dict[date, MarketContext],
    ) -> SwingBacktestSimulationResult:
        """Run daily portfolio walk-forward simulation."""
        cash = request.capital
        open_positions: list[SwingBacktestOpenPosition] = []
        trades: list[SwingBacktestTrade] = []
        candidate_observations: list[SwingBacktestCandidateObservation] = []
        equity_curve: list[SwingBacktestDailyEquity] = []
        skipped_no_cash = 0
        skipped_duplicate = 0
        skipped_no_forward_data = 0
        skipped_by_regime = 0
        exposure_days = 0

        for current_date in replay_dates:
            closed_today: list[SwingBacktestOpenPosition] = []
            for position in list(open_positions):
                exit_trade = self._exit_engine.maybe_exit(position, current_date, request)
                if exit_trade is None:
                    continue
                cash += exit_trade.exit_value - self._trade_cost(exit_trade.exit_value, request)
                trades.append(exit_trade)
                closed_today.append(position)

            if closed_today:
                open_positions = [
                    p for p in open_positions
                    if not any(
                        p.ticker == closed.ticker and p.entry_date == closed.entry_date
                        for closed in closed_today
                    )
                ]

            available_slots = request.max_positions - len(open_positions)
            if available_slots > 0:
                regime = regime_by_date.get(current_date)
                candidates = signals_by_date.get(current_date, [])
                candidate_observations.extend(
                    signal.candidate_observation
                    for signal in candidates
                    if signal.candidate_observation is not None
                )
                open_tickers = {p.ticker for p in open_positions}
                for entry_signal in candidates:
                    if not entry_signal.setup_evaluation.passed:
                        continue
                    candidate = entry_signal.candidate
                    if available_slots <= 0:
                        break
                    if candidate.ticker in open_tickers:
                        skipped_duplicate += 1
                        continue
                    regime_label = regime.regime.value if regime is not None else None
                    if not self._passes_regime_filter(regime_label, request):
                        skipped_by_regime += 1
                        continue
                    if not self._has_forward_data(candidate.ticker, current_date, request):
                        skipped_no_forward_data += 1
                        continue

                    position = self._position_builder.build(
                        candidate,
                        entry_signal.setup_evaluation,
                        current_date,
                        cash,
                        request,
                        regime,
                    )
                    if position is None:
                        skipped_no_cash += 1
                        continue

                    cash -= position.entry_value + position.entry_cost
                    open_positions.append(position)
                    open_tickers.add(candidate.ticker)
                    available_slots -= 1

            equity = cash + self._mark_to_market(open_positions, current_date)
            if open_positions:
                exposure_days += 1
            equity_curve.append(SwingBacktestDailyEquity(
                date=current_date,
                equity=equity,
                cash=cash,
                open_positions=len(open_positions),
            ))

        if replay_dates:
            final_date = replay_dates[-1]
            for position in list(open_positions):
                exit_trade = self._exit_engine.force_exit(position, final_date, request)
                if exit_trade is None:
                    continue
                cash += exit_trade.exit_value - self._trade_cost(exit_trade.exit_value, request)
                trades.append(exit_trade)
            final_equity = cash
        else:
            final_equity = request.capital

        return SwingBacktestSimulationResult(
            final_equity=final_equity,
            trades=trades,
            candidate_observations=candidate_observations,
            equity_curve=equity_curve,
            skipped_no_cash=skipped_no_cash,
            skipped_duplicate=skipped_duplicate,
            skipped_no_forward_data=skipped_no_forward_data,
            skipped_by_regime=skipped_by_regime,
            exposure_days=exposure_days,
        )

    def _passes_regime_filter(
        self,
        regime_label: str | None,
        request: SwingBacktestRequest,
    ) -> bool:
        if not request.allowed_regimes:
            return True
        if regime_label is None:
            return False
        allowed = {regime.upper() for regime in request.allowed_regimes}
        return regime_label.upper() in allowed

    def _has_forward_data(
        self,
        ticker: str,
        signal_date: date,
        request: SwingBacktestRequest,
    ) -> bool:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(days=request.forward_data_lookahead_days),
        )
        return any(c.date > signal_date for c in candles)

    def _candle_on(self, ticker: str, target_date: date) -> Candle | None:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=target_date,
            end_date=target_date,
        )
        return candles[0] if candles else None

    def _mark_to_market(
        self,
        positions: list[SwingBacktestOpenPosition],
        current_date: date,
    ) -> Decimal:
        value = Decimal("0")
        for position in positions:
            candle = self._candle_on(position.ticker, current_date)
            mark = candle.close if candle is not None else position.entry_price
            value += Decimal(position.shares) * mark
        return value

    def _trade_cost(self, value: Decimal, request: SwingBacktestRequest) -> Decimal:
        return value * request.cost_bps / Decimal("10000")
