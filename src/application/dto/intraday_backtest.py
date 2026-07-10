"""Request/response DTOs for the intraday backtesting workflow.

Layer: Application DTO
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

PER_TRADE_CAPITAL_CAP_PCT = Decimal("0.10")  # at most 10% of capital per trade


@dataclass(frozen=True)
class IntradayBacktestRequest:
    """Input parameters for a daily-OHLC intraday proxy simulation."""

    tickers: list[str]
    start_date: date
    end_date: date
    capital: Decimal = Decimal("100000000")
    risk_pct: Decimal = Decimal("0.01")           # 1% of capital at risk per trade
    max_daily_positions: int = 3
    atr_period: int = 14
    rsi_period: int = 14
    sma_period: int = 20
    atr_multiplier: Decimal = Decimal("1.0")
    max_stop_pct: Decimal = Decimal("0.07")        # 7% max stop distance
    rsi_overbought_threshold: Decimal = Decimal("75")
    atr_range_cap_min: Decimal = Decimal("0.01")   # 1% floor on ATR band
    atr_range_cap_max: Decimal = Decimal("0.05")   # 5% ceiling on ATR band
    broker_backing_window_days: int = 7
    broker_backing_threshold: float = 50.0
    fvwap_period: int = 20
    history_days: int = 60                         # min candle lookback per ticker
    include_wait: bool = False                     # treat WAIT as ENTER if True
    cost_bps: Decimal = Decimal("20")              # bps per side (round-trip = 2×)
    iev_top_n: int = 5                             # IEV top-N movers per day limit


# ── Result DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntradayBacktestTrade:
    """One completed intraday proxy trade (same-day in + out)."""

    ticker: str
    trade_date: date
    decision: str                    # "ENTER" or "WAIT" (when include_wait)
    opening_price: Decimal
    entry_price: Decimal
    exit_price: Decimal
    exit_reason: str                 # "target" | "stop" | "close" | "both_assume_stop"
    stop_price: Decimal
    target_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    exit_value: Decimal
    cost_total: Decimal
    gross_return_pct: float
    net_return_pct: float
    pnl: Decimal
    r_multiple: float | None
    # screener diagnostics
    trend: str | None
    rsi: float | None
    atr: float | None
    opening_broker_backing_tag: str | None
    opening_broker_backing_score: float | None
    opening_broker_buy_streak: int | None
    fvwap_discount_pct: float | None
    prev_high: Decimal | None
    entry_range_low: Decimal | None
    entry_range_high: Decimal | None
    same_day_both_breached: bool

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "trade_date": self.trade_date.isoformat(),
            "decision": self.decision,
            "opening_price": str(self.opening_price),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "exit_reason": self.exit_reason,
            "stop_price": str(self.stop_price),
            "target_price": str(self.target_price),
            "lots": self.lots,
            "shares": self.shares,
            "entry_value": str(self.entry_value),
            "exit_value": str(self.exit_value),
            "cost_total": str(self.cost_total),
            "gross_return_pct": self.gross_return_pct,
            "net_return_pct": self.net_return_pct,
            "pnl": str(self.pnl),
            "r_multiple": self.r_multiple,
            "trend": self.trend,
            "rsi": self.rsi,
            "atr": self.atr,
            "opening_broker_backing_tag": self.opening_broker_backing_tag,
            "opening_broker_backing_score": self.opening_broker_backing_score,
            "opening_broker_buy_streak": self.opening_broker_buy_streak,
            "fvwap_discount_pct": self.fvwap_discount_pct,
            "prev_high": str(self.prev_high) if self.prev_high is not None else None,
            "entry_range_low": (
                str(self.entry_range_low) if self.entry_range_low is not None else None
            ),
            "entry_range_high": (
                str(self.entry_range_high) if self.entry_range_high is not None else None
            ),
            "same_day_both_breached": self.same_day_both_breached,
        }


@dataclass(frozen=True)
class IntradayBacktestResponse:
    """Aggregate result of a daily-OHLC intraday proxy simulation."""

    # Config echo
    start_date: date
    end_date: date
    initial_capital: Decimal
    cost_bps: Decimal
    include_wait: bool
    max_daily_positions: int

    # Equity
    final_equity: Decimal
    total_return_pct: float
    max_drawdown_pct: float

    # Trade stats
    trade_count: int
    win_rate_pct: float | None
    avg_trade_return_pct: float | None
    avg_winner_pct: float | None
    avg_loser_pct: float | None
    profit_factor: float | None
    expectancy_pct: float | None
    avg_r_multiple: float | None
    exit_reason_counts: dict[str, int]
    decisions: dict[str, int]

    # Days
    trading_days: int
    days_with_trades: int

    # Signal-quality breakdowns
    by_opening_broker_backing_tag: list[dict]
    by_fvwap_sign: list[dict]
    by_rsi_bucket: list[dict]
    by_ticker: list[dict]

    trades: list[IntradayBacktestTrade] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
