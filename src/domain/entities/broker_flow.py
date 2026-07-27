"""
Broker flow entities - pure domain models.

These entities represent broker trading activity and foreign flow data.
No external dependencies. Framework-agnostic.

Layer: Domain
Dependencies: None (only standard library)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class BrokerType(Enum):
    """Type of broker by investor category."""

    FOREIGN = "FOREIGN"  # ASING - Foreign investors
    LOCAL = "LOCAL"  # LOKAL - Domestic investors
    UNKNOWN = "UNKNOWN"

    @classmethod
    def parse(cls, value: str) -> "BrokerType":
        """Parse canonical uppercase and legacy lowercase broker type values."""
        normalized = value.strip().upper().replace("-", "_")
        for broker_type in cls:
            if normalized in {broker_type.name, broker_type.value}:
                return broker_type
        valid = [broker_type.value for broker_type in cls]
        raise ValueError(f"Invalid broker type '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class BrokerTransaction:
    """
    Immutable representation of a broker's trading activity for a single day.

    Attributes:
        broker_code: Broker identifier code (e.g., 'YP', 'CC', 'MS')
        broker_name: Human-readable broker name
        broker_type: Foreign or local investor
        buy_lot: Number of lots bought
        sell_lot: Number of lots sold
        buy_value: Total value bought (IDR)
        sell_value: Total value sold (IDR)
        avg_buy_price: Average buy price per share
        avg_sell_price: Average sell price per share
    """

    broker_code: str
    broker_name: str
    broker_type: BrokerType
    buy_lot: int
    sell_lot: int
    buy_value: Decimal
    sell_value: Decimal
    avg_buy_price: Decimal
    avg_sell_price: Decimal

    def __post_init__(self) -> None:
        """Validate broker transaction data."""
        if not self.broker_code:
            raise ValueError("Broker code cannot be empty")
        if self.buy_lot < 0 or self.sell_lot < 0:
            raise ValueError("Lot counts cannot be negative")
        if self.buy_value < 0 or self.sell_value < 0:
            raise ValueError("Values cannot be negative")

    @property
    def net_lot(self) -> int:
        """Net lots (positive = net buyer, negative = net seller)."""
        return self.buy_lot - self.sell_lot

    @property
    def net_value(self) -> Decimal:
        """Net value (positive = net buyer, negative = net seller)."""
        return self.buy_value - self.sell_value

    @property
    def is_net_buyer(self) -> bool:
        """True if broker is a net buyer by value."""
        return self.net_value > Decimal("0")

    @property
    def is_net_seller(self) -> bool:
        """True if broker is a net seller by value."""
        return self.net_value < Decimal("0")

    @property
    def is_foreign(self) -> bool:
        """True if broker is foreign (ASING)."""
        return self.broker_type == BrokerType.FOREIGN

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "broker_code": self.broker_code,
            "broker_name": self.broker_name,
            "broker_type": self.broker_type.value,
            "buy_lot": self.buy_lot,
            "sell_lot": self.sell_lot,
            "buy_value": str(self.buy_value),
            "sell_value": str(self.sell_value),
            "avg_buy_price": str(self.avg_buy_price),
            "avg_sell_price": str(self.avg_sell_price),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrokerTransaction":
        """Create BrokerTransaction from dictionary."""
        return cls(
            broker_code=data["broker_code"],
            broker_name=data["broker_name"],
            broker_type=BrokerType.parse(data["broker_type"]),
            buy_lot=int(data["buy_lot"]),
            sell_lot=int(data["sell_lot"]),
            buy_value=Decimal(data["buy_value"]),
            sell_value=Decimal(data["sell_value"]),
            avg_buy_price=Decimal(data["avg_buy_price"]),
            avg_sell_price=Decimal(data["avg_sell_price"]),
        )


@dataclass(frozen=True)
class BrokerSummary:
    """
    Aggregated broker data for a specific ticker and date.

    Contains top buyers/sellers and aggregate foreign flow metrics.

    Attributes:
        ticker: Stock ticker symbol
        date: Trading date
        top_buyers: Top 10 brokers by net buy value
        top_sellers: Top 10 brokers by net sell value
        foreign_buy_value: Total foreign buy value (IDR)
        foreign_sell_value: Total foreign sell value (IDR)
        foreign_buy_lot: Total foreign buy lots
        foreign_sell_lot: Total foreign sell lots
        total_value: Total trading value for the day
        total_lot: Total trading lots for the day
    """

    ticker: str
    date: date
    top_buyers: tuple[BrokerTransaction, ...]
    top_sellers: tuple[BrokerTransaction, ...]
    foreign_buy_value: Decimal
    foreign_sell_value: Decimal
    foreign_buy_lot: int
    foreign_sell_lot: int
    total_value: Decimal
    total_lot: int
    source: str = "idx"  # 'idx' | 'stockbit' | 'csv-idx' | 'csv-stockbit'

    def __post_init__(self) -> None:
        """Validate broker summary data."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")

    @property
    def foreign_net_value(self) -> Decimal:
        """Net foreign flow (positive = net buy, negative = net sell)."""
        return self.foreign_buy_value - self.foreign_sell_value

    @property
    def foreign_net_lot(self) -> int:
        """Net foreign lot flow."""
        return self.foreign_buy_lot - self.foreign_sell_lot

    @property
    def is_foreign_accumulating(self) -> bool:
        """True if foreign investors are net buyers."""
        return self.foreign_net_value > Decimal("0")

    @property
    def foreign_flow_ratio(self) -> Decimal:
        """Foreign net flow as percentage of total value (-100 to +100)."""
        if self.total_value == Decimal("0"):
            return Decimal("0")
        return (self.foreign_net_value / self.total_value) * Decimal("100")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "date": self.date.isoformat(),
            "top_buyers": [b.to_dict() for b in self.top_buyers],
            "top_sellers": [s.to_dict() for s in self.top_sellers],
            "foreign_buy_value": str(self.foreign_buy_value),
            "foreign_sell_value": str(self.foreign_sell_value),
            "foreign_buy_lot": self.foreign_buy_lot,
            "foreign_sell_lot": self.foreign_sell_lot,
            "total_value": str(self.total_value),
            "total_lot": self.total_lot,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrokerSummary":
        """Create BrokerSummary from dictionary."""
        return cls(
            ticker=data["ticker"],
            date=(
                date.fromisoformat(data["date"]) if isinstance(data["date"], str) else data["date"]
            ),
            top_buyers=tuple(BrokerTransaction.from_dict(b) for b in data.get("top_buyers", [])),
            top_sellers=tuple(BrokerTransaction.from_dict(s) for s in data.get("top_sellers", [])),
            foreign_buy_value=Decimal(data["foreign_buy_value"]),
            foreign_sell_value=Decimal(data["foreign_sell_value"]),
            foreign_buy_lot=int(data["foreign_buy_lot"]),
            foreign_sell_lot=int(data["foreign_sell_lot"]),
            total_value=Decimal(data["total_value"]),
            total_lot=int(data["total_lot"]),
            source=data.get("source", "idx"),
        )


@dataclass(frozen=True)
class ForeignFlowPoint:
    """
    Single data point in the historical foreign flow time-series for a stock.

    Returned by the stock-centric historical endpoint (daily/weekly aggregate
    foreign flow). Used for backfilling and trend context.
    """

    ticker: str
    date: date
    net_val: Decimal  # foreign net value (positive = net buy)
    net_lot: int
    avg_price: Decimal  # average price for the period; 'idx'=close price approx, 'stockbit'=exact
    source: str = "stockbit"  # e.g. 'idx' | 'stockbit'


@dataclass(frozen=True)
class ForeignFlowSnapshot:
    """
    Lightweight snapshot of foreign broker aggregate flow for a stock.

    Returned by the broker-centric universe scan (which stocks are foreign
    brokers accumulating?). Does NOT include named broker breakdown.
    Use BrokerSummary for the full named breakdown.
    """

    ticker: str
    date: date
    net_val: Decimal  # positive = net buy, negative = net sell
    net_lot: int
    nval_trend: tuple[ForeignFlowPoint, ...] = ()  # 7-day embedded trend from universe scan

    @property
    def is_accumulating(self) -> bool:
        return self.net_val > Decimal("0")


@dataclass(frozen=True)
class BrokerDailyFlow:
    """
    Real per-day trading activity for a single named broker on a single stock.

    Sourced from the Stockbit /order-trade/broker/activity/historical endpoint
    with interval=INTERVAL_DAILY. One row per (ticker, date, broker_code).

    NOTE ON IMBALANCE:
    In a closed stock market, the sum of net flows across all brokers on a date
    should equal zero. However, since the database only tracks a subset of primary
    brokers (e.g. key retail and institutional desks configured in tracked_broker_codes),
    summing net_lot or net_value across all records for a particular ticker and date
    will result in a systematic imbalance (non-zero sum). This is an expected property
    of the top-broker data feed.

    This is NEVER an aggregate — each row represents exactly one trading session.
    The accumulation screen uses this for accurate window-based broker analysis.
    """

    ticker: str
    broker_code: str
    broker_name: str
    date: date
    buy_lot: int
    sell_lot: int
    net_lot: int
    buy_value: Decimal
    sell_value: Decimal
    net_value: Decimal
    avg_buy_price: Decimal  # avg price at which broker bought (buy_summary.avg_price)
    avg_sell_price: Decimal  # avg price at which broker sold (sell_summary.avg_price)
    avg_price: Decimal  # net_summary.avg_price (dominant-side price; kept for compat)
    buy_pct: float  # broker's buy lot as % of total market buy that day
    sell_pct: float  # broker's sell lot as % of total market sell that day
    source: str = "stockbit"

    @property
    def is_net_buyer(self) -> bool:
        return self.net_value > Decimal("0")

    @property
    def is_net_seller(self) -> bool:
        return self.net_value < Decimal("0")
