"""
Backtest engine domain service.

Pure domain logic for executing backtest simulations.
No I/O, no framework dependencies.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN

from src.domain.entities.backtest_trade import BacktestTrade
from src.domain.entities.candle import Candle
from src.domain.value_objects.backtest_result import BacktestResult
from src.domain.value_objects.trade_action import TradeAction


@dataclass
class _Position:
    """Internal mutable state for tracking open position."""

    entry_date: date
    entry_price: Decimal
    entry_rule: str
    shares: int


class BacktestEngine:
    """
    Pure domain engine for backtest simulation.

    Stateless service - receives all inputs and returns result.
    Does not know about rules, indicators, or risk levels.
    Just executes ENTER_LONG/EXIT_LONG/HOLD/FLAT actions on candles.

    The engine is intentionally simple for Phase 1:
    - Single position (all-in)
    - Long-only
    - No slippage or commissions
    """

    def __init__(self, initial_capital: Decimal):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital for simulation
        """
        if initial_capital <= Decimal("0"):
            raise ValueError("Initial capital must be positive")
        self._initial_capital = initial_capital

    def run(
        self,
        candles: list[Candle],
        actions: list[tuple[date, TradeAction, str]],
        strategy_name: str,
    ) -> BacktestResult:
        """
        Execute backtest with pre-computed actions.

        Domain stays pure - doesn't know about rules or indicators.
        Just executes trade actions on candles.

        Args:
            candles: Historical price data sorted by date ascending
            actions: List of (date, action, rule_name) tuples
            strategy_name: Name of the strategy for result

        Returns:
            BacktestResult with trades and metrics

        Raises:
            ValueError: If candles is empty or invalid
        """
        if not candles:
            raise ValueError("Cannot run backtest with empty candles")

        if not strategy_name:
            raise ValueError("Strategy name cannot be empty")

        # Sort candles by date to ensure chronological order
        sorted_candles = sorted(candles, key=lambda c: c.date)

        # Build action lookup by date
        action_by_date: dict[date, tuple[TradeAction, str]] = {
            d: (action, rule) for d, action, rule in actions
        }

        # Build candle lookup by date for price retrieval
        candle_by_date: dict[date, Candle] = {c.date: c for c in sorted_candles}

        # Simulation state
        capital = self._initial_capital
        position: _Position | None = None
        completed_trades: list[BacktestTrade] = []
        equity_curve: list[Decimal] = [capital]

        # Run simulation
        for candle in sorted_candles:
            action, rule_name = action_by_date.get(candle.date, (TradeAction.HOLD, "default"))

            if action == TradeAction.ENTER_LONG and position is None:
                # Enter new position at close price
                shares = self._calculate_shares(capital, candle.close)
                if shares > 0:
                    position = _Position(
                        entry_date=candle.date,
                        entry_price=candle.close,
                        entry_rule=rule_name,
                        shares=shares,
                    )
                    # Deduct capital
                    capital -= position.shares * position.entry_price

            elif action == TradeAction.EXIT_LONG and position is not None:
                # Exit position at close price
                trade = BacktestTrade(
                    entry_date=position.entry_date,
                    entry_price=position.entry_price,
                    entry_rule=position.entry_rule,
                    exit_date=candle.date,
                    exit_price=candle.close,
                    exit_rule=rule_name,
                    shares=position.shares,
                )
                completed_trades.append(trade)
                # Add proceeds to capital
                capital += position.shares * candle.close
                position = None

            # Update equity curve (capital + position value at current close)
            current_equity = capital
            if position is not None:
                current_equity += position.shares * candle.close
            equity_curve.append(current_equity)

        # Close any open position at the end (forced exit)
        if position is not None:
            last_candle = sorted_candles[-1]
            trade = BacktestTrade(
                entry_date=position.entry_date,
                entry_price=position.entry_price,
                entry_rule=position.entry_rule,
                exit_date=last_candle.date,
                exit_price=last_candle.close,
                exit_rule="end_of_data",
                shares=position.shares,
            )
            completed_trades.append(trade)
            capital += position.shares * last_candle.close

        # Calculate max drawdown
        max_drawdown_pct = self._calculate_max_drawdown(equity_curve)

        return BacktestResult(
            ticker=sorted_candles[0].ticker,
            strategy_name=strategy_name,
            start_date=sorted_candles[0].date,
            end_date=sorted_candles[-1].date,
            initial_capital=self._initial_capital,
            final_capital=capital,
            trades=tuple(completed_trades),
            max_drawdown_pct=max_drawdown_pct,
        )

    def _calculate_shares(self, capital: Decimal, price: Decimal) -> int:
        """
        Calculate number of shares to buy (all-in).

        Uses integer division to ensure whole shares.
        Rounds down to avoid exceeding available capital.

        Args:
            capital: Available capital
            price: Price per share

        Returns:
            Number of whole shares to purchase
        """
        if price <= Decimal("0"):
            return 0
        # Round down to whole shares
        shares = (capital / price).to_integral_value(rounding=ROUND_DOWN)
        return int(shares)

    def _calculate_max_drawdown(self, equity_curve: list[Decimal]) -> Decimal:
        """
        Calculate maximum peak-to-trough decline as percentage.

        Args:
            equity_curve: List of equity values over time

        Returns:
            Maximum drawdown as a percentage (e.g., 10.5 for 10.5%)
        """
        if len(equity_curve) < 2:
            return Decimal("0")

        peak = equity_curve[0]
        max_drawdown = Decimal("0")

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            if peak > Decimal("0"):
                drawdown = ((peak - equity) / peak) * Decimal("100")
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        return max_drawdown
