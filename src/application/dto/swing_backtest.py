"""Data transfer objects for swing backtests.

Layer: Application DTO
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.accumulation_screen import AccumulationCandidate

# NOTE: TEMPORARY COMPATIBILITY EXCEPTION
# To avoid breaking existing downstream adapters and CLI workflows, these imports of configuration
# and reporting summary classes from use cases/services are kept here as a temporary exception.
# A future refactoring will migrate these configurations to a pure config/DTO directory.
from src.application.services.swing_backtest_attribution import (
    AttributionBucketPolicy,
    SwingBacktestAttributionSummary,
)
from src.application.use_case.evaluate_swing_setup_use_case import SwingSetupCatalogConfig
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate

FOREIGN_BOUNCE_SETUP = "foreign-bounce"
DEFAULT_SWING_COST_BPS = Decimal("20")


@dataclass(frozen=True)
class SwingBacktestRequest:
    """Input parameters for a walk-forward swing workflow backtest."""

    tickers: list[str]
    start_date: date
    end_date: date
    setup: str = FOREIGN_BOUNCE_SETUP
    capital: Decimal = Decimal("100000000")
    risk_pct: Decimal = Decimal("0.01")
    max_positions: int = 5
    window_days: int = 7
    min_net_buy_days: int = 2
    min_vwap_disc_pct: float = 3.0
    trend: str = "SIDE"
    min_flow_pct: float = 5.0
    max_rsi: float = 60.0
    take_profit_pct: Decimal = Decimal("5")
    stop_loss_pct: Decimal = Decimal("5")
    max_hold_days: int = 10
    cost_bps: Decimal = DEFAULT_SWING_COST_BPS
    include_regime: bool = False
    benchmark_ticker: str = "IHSG"
    allowed_regimes: tuple[str, ...] = ()
    setup_targets: dict[str, Any] | None = None
    setup_config: SwingSetupCatalogConfig = field(default_factory=SwingSetupCatalogConfig)
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0
    ex_date_warning_days: int = 10
    forward_data_lookahead_days: int = 45
    same_day_exit_priority: str = "stop_first"
    attribution_bucket_policy: AttributionBucketPolicy = field(
        default_factory=AttributionBucketPolicy
    )


@dataclass(frozen=True)
class SwingBacktestTrade:
    """One completed walk-forward swing trade."""

    ticker: str
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    exit_value: Decimal
    gross_return_pct: float
    net_return_pct: float
    pnl: Decimal
    holding_days: int
    exit_reason: str
    accum_score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None = None
    setup_match: str | None = None
    setup_failed_reasons: tuple[str, ...] = ()
    setup_gates: tuple[SetupGate, ...] = ()
    trade_setup_action: str | None = None
    signal_score: int | None = None
    signal_strength: str | None = None
    signal_entry_quality: str | None = None
    signal_breakdown: tuple[tuple[str, float], ...] = ()
    risk_status: str | None = None
    risk_gate: str | None = None
    risk_confidence: int | None = None
    market_context: MarketContext | None = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "lots": self.lots,
            "shares": self.shares,
            "entry_value": str(self.entry_value),
            "exit_value": str(self.exit_value),
            "gross_return_pct": self.gross_return_pct,
            "net_return_pct": self.net_return_pct,
            "pnl": str(self.pnl),
            "holding_days": self.holding_days,
            "exit_reason": self.exit_reason,
            "accum_score": self.accum_score,
            "flow_pct": self.flow_pct,
            "vwap_disc_pct": self.vwap_disc_pct,
            "rsi": self.rsi,
            "regime": self.regime,
            "setup_match": self.setup_match,
            "setup_failed_reasons": list(self.setup_failed_reasons),
            "setup_gates": [
                {
                    "label": gate.label,
                    "passed": gate.passed,
                    "actual": gate.actual,
                    "required": gate.required,
                }
                for gate in self.setup_gates
            ],
            "trade_setup_action": self.trade_setup_action,
            "signal_score": self.signal_score,
            "signal_strength": self.signal_strength,
            "signal_entry_quality": self.signal_entry_quality,
            "signal_breakdown": dict(self.signal_breakdown),
            "risk_status": self.risk_status,
            "risk_gate": self.risk_gate,
            "risk_confidence": self.risk_confidence,
            "market_context": self.market_context.to_dict() if self.market_context else None,
        }


@dataclass(frozen=True)
class SwingBacktestCandidateObservation:
    """Screened candidate forward-return observation for setup/risk tuning."""

    ticker: str
    signal_date: date
    entry_price: Decimal
    observation_exit_date: date
    observation_exit_price: Decimal
    forward_return_pct: float
    setup_match: str | None = None
    setup_failed_reasons: tuple[str, ...] = ()
    setup_gates: tuple[SetupGate, ...] = ()
    trade_setup_action: str | None = None
    signal_score: int | None = None
    signal_strength: str | None = None
    signal_breakdown: tuple[tuple[str, float], ...] = ()
    risk_status: str | None = None
    risk_gate: str | None = None
    regime: str | None = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "signal_date": self.signal_date.isoformat(),
            "entry_price": str(self.entry_price),
            "observation_exit_date": self.observation_exit_date.isoformat(),
            "observation_exit_price": str(self.observation_exit_price),
            "forward_return_pct": self.forward_return_pct,
            "setup_match": self.setup_match,
            "setup_failed_reasons": list(self.setup_failed_reasons),
            "setup_gates": [
                {
                    "label": gate.label,
                    "passed": gate.passed,
                    "actual": gate.actual,
                    "required": gate.required,
                }
                for gate in self.setup_gates
            ],
            "trade_setup_action": self.trade_setup_action,
            "signal_score": self.signal_score,
            "signal_strength": self.signal_strength,
            "signal_breakdown": dict(self.signal_breakdown),
            "risk_status": self.risk_status,
            "risk_gate": self.risk_gate,
            "regime": self.regime,
        }


@dataclass(frozen=True)
class SwingBacktestDailyEquity:
    """Daily portfolio equity point."""

    date: date
    equity: Decimal
    cash: Decimal
    open_positions: int

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "equity": str(self.equity),
            "cash": str(self.cash),
            "open_positions": self.open_positions,
        }


@dataclass(frozen=True)
class SwingBacktestRegimeStat:
    """Trade performance grouped by entry-date market regime."""

    regime: str
    count: int
    avg_return_pct: float | None
    win_rate_pct: float | None
    total_pnl: Decimal

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "count": self.count,
            "avg_return_pct": self.avg_return_pct,
            "win_rate_pct": self.win_rate_pct,
            "total_pnl": str(self.total_pnl),
        }


@dataclass(frozen=True)
class SwingBacktestResponse:
    """Portfolio-level walk-forward result."""

    setup: str
    start_date: date
    end_date: date
    initial_capital: Decimal
    cost_bps: Decimal
    final_equity: Decimal
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float | None
    avg_trade_return_pct: float | None
    profit_factor: float | None
    exposure_pct: float
    skipped_no_cash: int
    skipped_duplicate: int
    skipped_no_forward_data: int
    skipped_by_regime: int
    trades: list[SwingBacktestTrade] = field(default_factory=list)
    candidate_observations: list[SwingBacktestCandidateObservation] = field(
        default_factory=list
    )
    equity_curve: list[SwingBacktestDailyEquity] = field(default_factory=list)
    regime_stats: list[SwingBacktestRegimeStat] = field(default_factory=list)
    regime_by_date: dict[date, MarketContext] = field(default_factory=dict)
    attribution_summary: SwingBacktestAttributionSummary = field(
        default_factory=SwingBacktestAttributionSummary
    )
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SwingBacktestEntrySignal:
    """Lightweight DTO for entry signal orchestration across modules."""

    candidate: AccumulationCandidate
    setup_evaluation: SetupEvaluation
    candidate_observation: SwingBacktestCandidateObservation | None = None
