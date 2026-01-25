"""
OHLCV Candle entity - pure domain model.

This entity represents a single candlestick of market data.
No external dependencies. Framework-agnostic.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    """
    Immutable representation of daily OHLCV market data.

    Attributes:
        ticker: Stock ticker symbol (e.g., 'BBCA')
        date: Trading date
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
    """

    ticker: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        """Validate candle data integrity."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.high < self.low:
            raise ValueError("High price cannot be less than low price")
        if self.open < Decimal("0") or self.close < Decimal("0"):
            raise ValueError("Prices cannot be negative")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "date": self.date.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Candle":
        """Create Candle from dictionary."""
        return cls(
            ticker=data["ticker"],
            date=date.fromisoformat(data["date"]) if isinstance(data["date"], str) else data["date"],
            open=Decimal(data["open"]),
            high=Decimal(data["high"]),
            low=Decimal(data["low"]),
            close=Decimal(data["close"]),
            volume=int(data["volume"]),
        )
