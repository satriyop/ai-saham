"""
Backtest trade entity - pure domain model.

This entity represents a completed trade in a backtest simulation.
No external dependencies. Framework-agnostic.

Layer: Domain
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BacktestTrade:
    """
    Immutable representation of a completed backtest trade.

    Represents a round-trip trade (entry + exit) in a backtest simulation.
    All monetary values use Decimal for precision.

    Attributes:
        entry_date: Date the position was opened
        entry_price: Price at which position was entered
        entry_rule: Name of the rule that triggered entry
        exit_date: Date the position was closed
        exit_price: Price at which position was exited
        exit_rule: Name of the rule that triggered exit
        shares: Number of shares traded
    """

    entry_date: date
    entry_price: Decimal
    entry_rule: str
    exit_date: date
    exit_price: Decimal
    exit_rule: str
    shares: int

    def __post_init__(self) -> None:
        """Validate trade data integrity."""
        if self.entry_price <= Decimal("0"):
            raise ValueError("Entry price must be positive")
        if self.exit_price <= Decimal("0"):
            raise ValueError("Exit price must be positive")
        if self.shares <= 0:
            raise ValueError("Shares must be positive")
        if self.exit_date < self.entry_date:
            raise ValueError("Exit date cannot be before entry date")
        if not self.entry_rule:
            raise ValueError("Entry rule cannot be empty")
        if not self.exit_rule:
            raise ValueError("Exit rule cannot be empty")

    @property
    def pnl(self) -> Decimal:
        """
        Calculate profit/loss in absolute terms.

        Returns:
            Total profit or loss for this trade
        """
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def pnl_percent(self) -> Decimal:
        """
        Calculate profit/loss as a percentage.

        Returns:
            Percentage return for this trade
        """
        return ((self.exit_price - self.entry_price) / self.entry_price) * Decimal("100")

    @property
    def holding_days(self) -> int:
        """
        Calculate number of days position was held.

        Returns:
            Number of calendar days between entry and exit
        """
        return (self.exit_date - self.entry_date).days

    @property
    def is_winning(self) -> bool:
        """
        Check if trade was profitable.

        Returns:
            True if trade resulted in profit, False otherwise
        """
        return self.pnl > Decimal("0")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "entry_date": self.entry_date.isoformat(),
            "entry_price": str(self.entry_price),
            "entry_rule": self.entry_rule,
            "exit_date": self.exit_date.isoformat(),
            "exit_price": str(self.exit_price),
            "exit_rule": self.exit_rule,
            "shares": self.shares,
            "pnl": str(self.pnl),
            "pnl_percent": str(self.pnl_percent),
            "holding_days": self.holding_days,
            "is_winning": self.is_winning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BacktestTrade":
        """Create BacktestTrade from dictionary."""
        return cls(
            entry_date=(
                date.fromisoformat(data["entry_date"])
                if isinstance(data["entry_date"], str)
                else data["entry_date"]
            ),
            entry_price=Decimal(data["entry_price"]),
            entry_rule=data["entry_rule"],
            exit_date=(
                date.fromisoformat(data["exit_date"])
                if isinstance(data["exit_date"], str)
                else data["exit_date"]
            ),
            exit_price=Decimal(data["exit_price"]),
            exit_rule=data["exit_rule"],
            shares=int(data["shares"]),
        )
