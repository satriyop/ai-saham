"""
Backtest result value object.

Contains the complete results of a backtest simulation including
trades and performance metrics.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.domain.entities.backtest_trade import BacktestTrade


@dataclass(frozen=True)
class BacktestResult:
    """
    Immutable representation of backtest results.

    Contains the complete results of a backtest simulation,
    including all trades and raw metrics as Decimal values.

    Attributes:
        ticker: Stock ticker that was backtested
        strategy_name: Name of the strategy used
        start_date: First date in backtest period
        end_date: Last date in backtest period
        initial_capital: Starting capital for simulation
        final_capital: Ending capital after all trades
        trades: Tuple of all completed trades
        max_drawdown_pct: Maximum peak-to-trough decline as percentage
    """

    ticker: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: Decimal
    final_capital: Decimal
    trades: tuple[BacktestTrade, ...]
    max_drawdown_pct: Decimal

    def __post_init__(self) -> None:
        """Validate result data integrity."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if not self.strategy_name:
            raise ValueError("Strategy name cannot be empty")
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if self.initial_capital <= Decimal("0"):
            raise ValueError("Initial capital must be positive")
        if self.final_capital < Decimal("0"):
            raise ValueError("Final capital cannot be negative")

    @property
    def total_return_pct(self) -> Decimal:
        """
        Calculate total return as a percentage.

        Returns:
            Percentage return over the backtest period
        """
        if self.initial_capital == Decimal("0"):
            return Decimal("0")
        return ((self.final_capital - self.initial_capital) / self.initial_capital) * Decimal("100")

    @property
    def trade_count(self) -> int:
        """
        Get total number of completed trades.

        Returns:
            Number of round-trip trades
        """
        return len(self.trades)

    @property
    def win_rate(self) -> Decimal:
        """
        Calculate win rate as a percentage.

        Returns:
            Percentage of trades that were profitable
        """
        if not self.trades:
            return Decimal("0")
        winning_trades = sum(1 for t in self.trades if t.is_winning)
        return (Decimal(winning_trades) / Decimal(len(self.trades))) * Decimal("100")

    @property
    def profit_factor(self) -> Decimal:
        """
        Calculate profit factor (gross profit / gross loss).

        A profit factor > 1 indicates the strategy is profitable overall.

        Returns:
            Ratio of gross profits to gross losses, or 0 if no losses
        """
        gross_profit = sum((t.pnl for t in self.trades if t.pnl > Decimal("0")), Decimal("0"))
        gross_loss = abs(sum((t.pnl for t in self.trades if t.pnl < Decimal("0")), Decimal("0")))

        if gross_loss == Decimal("0"):
            if gross_profit > Decimal("0"):
                # All winning trades, return infinity-like indicator
                return Decimal("999.99")
            return Decimal("0")
        return gross_profit / gross_loss

    @property
    def total_pnl(self) -> Decimal:
        """
        Calculate total profit/loss across all trades.

        Returns:
            Sum of all trade P&L
        """
        return sum((t.pnl for t in self.trades), Decimal("0"))

    @property
    def winning_trades(self) -> int:
        """
        Count of profitable trades.

        Returns:
            Number of trades with positive P&L
        """
        return sum(1 for t in self.trades if t.is_winning)

    @property
    def losing_trades(self) -> int:
        """
        Count of unprofitable trades.

        Returns:
            Number of trades with negative or zero P&L
        """
        return sum(1 for t in self.trades if not t.is_winning)

    @property
    def avg_win(self) -> Decimal:
        """
        Average profit of winning trades.

        Returns:
            Average P&L of profitable trades, or 0 if none
        """
        winners = [t.pnl for t in self.trades if t.is_winning]
        if not winners:
            return Decimal("0")
        return sum(winners) / Decimal(len(winners))

    @property
    def avg_loss(self) -> Decimal:
        """
        Average loss of losing trades.

        Returns:
            Average P&L (negative) of unprofitable trades, or 0 if none
        """
        losers = [t.pnl for t in self.trades if not t.is_winning]
        if not losers:
            return Decimal("0")
        return sum(losers) / Decimal(len(losers))

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": str(self.initial_capital),
            "final_capital": str(self.final_capital),
            "trades": [t.to_dict() for t in self.trades],
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "total_return_pct": str(self.total_return_pct),
            "trade_count": self.trade_count,
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
        }
