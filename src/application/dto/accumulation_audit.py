"""
DTOs and policy objects for the foreign accumulation historical audit.

Layer: Application
AI usage: None
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

DEFAULT_AUDIT_GROUP_DIMENSIONS = (
    "foreign_flow_score",
    "streak",
    "flow_pct",
    "vwap_disc_pct",
    "rsi",
    "bb_pctile",
    "trend",
    "broker_quality",
)


@dataclass(frozen=True)
class AuditBucketPolicy:
    """Bucket boundaries used by accumulation-audit learning summaries."""

    # Edges are on the live 0-100 foreign_flow_score scale. Audit replay always
    # recomputes scores fresh via ScoreForeignFlowUseCase, so all records in a
    # run share the current scale; previously-exported audit JSON/CSV artifacts
    # are on their era's scale and must not be re-bucketed with these edges.
    foreign_flow_score: tuple[float, ...] = (33.3, 58.3)
    streak: tuple[int, ...] = (3, 5)
    flow_pct: tuple[float, ...] = (5.0, 15.0)
    vwap_disc_pct: tuple[float, ...] = (0.0, 5.0)
    rsi: tuple[float, ...] = (30.0, 45.0, 60.0)
    bb_pctile: tuple[float, ...] = (0.20, 0.40)


@dataclass(frozen=True)
class AccumulationAuditPolicy:
    """Tunable measurement policy for historical accumulation audits."""

    forward_return_horizons: tuple[int, ...] = (5, 10, 20)
    forward_fetch_buffer_days: int = 40
    exit_fetch_buffer_days: int = 40
    same_day_exit_priority: str = "stop_first"
    broker_quality_window_sessions: int = 5
    group_dimensions: tuple[str, ...] = DEFAULT_AUDIT_GROUP_DIMENSIONS
    buckets: AuditBucketPolicy = field(default_factory=AuditBucketPolicy)


@dataclass(frozen=True)
class AuditRecord:
    """One replayed accumulation signal and its forward outcomes."""

    signal_date: date
    ticker: str
    foreign_flow_score: float
    streak: int
    net_buy_ratio: float
    total_net_value: Decimal
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    bb_pctile: float | None
    trend: str
    broker_quality: str
    current_price: Decimal
    return_5d_pct: float | None
    return_10d_pct: float | None
    return_20d_pct: float | None
    max_upside_pct: float | None
    max_drawdown_pct: float | None
    forward_returns_pct: dict[int, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON/CSV friendly primitives."""
        return {
            "signal_date": self.signal_date.isoformat(),
            "ticker": self.ticker,
            "foreign_flow_score": self.foreign_flow_score,
            "streak": self.streak,
            "net_buy_ratio": round(self.net_buy_ratio, 4),
            "total_net_value": str(self.total_net_value),
            "flow_pct": round(self.flow_pct, 4) if self.flow_pct is not None else None,
            "vwap_disc_pct": round(self.vwap_disc_pct, 4)
            if self.vwap_disc_pct is not None else None,
            "rsi": round(self.rsi, 4) if self.rsi is not None else None,
            "bb_pctile": round(self.bb_pctile, 4) if self.bb_pctile is not None else None,
            "trend": self.trend,
            "broker_quality": self.broker_quality,
            "current_price": str(self.current_price),
            "return_5d_pct": self.return_5d_pct,
            "return_10d_pct": self.return_10d_pct,
            "return_20d_pct": self.return_20d_pct,
            "max_upside_pct": self.max_upside_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            **{
                f"return_{horizon}d_pct": value
                for horizon, value in sorted(self.forward_returns_pct.items())
                if horizon not in {5, 10, 20}
            },
        }


@dataclass(frozen=True)
class AuditGroupStat:
    """Performance statistics for one grouped signal bucket."""

    dimension: str
    bucket: str
    count: int
    avg_return_5d_pct: float | None
    avg_return_10d_pct: float | None
    avg_return_20d_pct: float | None
    win_rate_10d_pct: float | None
    avg_max_upside_pct: float | None
    avg_max_drawdown_pct: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "bucket": self.bucket,
            "count": self.count,
            "avg_return_5d_pct": self.avg_return_5d_pct,
            "avg_return_10d_pct": self.avg_return_10d_pct,
            "avg_return_20d_pct": self.avg_return_20d_pct,
            "win_rate_10d_pct": self.win_rate_10d_pct,
            "avg_max_upside_pct": self.avg_max_upside_pct,
            "avg_max_drawdown_pct": self.avg_max_drawdown_pct,
        }


@dataclass(frozen=True)
class ExitSimulationStat:
    """Aggregate outcome for one take-profit/stop-loss/max-hold exit rule."""

    take_profit_pct: float
    stop_loss_pct: float
    max_hold_days: int
    count: int
    avg_return_pct: float | None
    win_rate_pct: float | None
    avg_holding_days: float | None
    stop_rate_pct: float | None
    target_rate_pct: float | None
    max_hold_rate_pct: float | None
    avg_max_drawdown_pct: float | None

    def to_dict(self) -> dict:
        return {
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "max_hold_days": self.max_hold_days,
            "count": self.count,
            "avg_return_pct": self.avg_return_pct,
            "win_rate_pct": self.win_rate_pct,
            "avg_holding_days": self.avg_holding_days,
            "stop_rate_pct": self.stop_rate_pct,
            "target_rate_pct": self.target_rate_pct,
            "max_hold_rate_pct": self.max_hold_rate_pct,
            "avg_max_drawdown_pct": self.avg_max_drawdown_pct,
        }


@dataclass(frozen=True)
class AccumulationAuditResponse:
    """Audit output containing raw records and grouped summaries."""

    start_date: date
    end_date: date
    window_days: int
    total_replay_dates: int
    total_tickers: int
    total_records: int
    skipped_no_forward_data: int
    records: list[AuditRecord] = field(default_factory=list)
    group_stats: list[AuditGroupStat] = field(default_factory=list)
    exit_simulations: list[ExitSimulationStat] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AccumulationAuditRequest:
    """Input parameters for historical accumulation-signal audit."""

    tickers: list[str]
    start_date: date
    end_date: date
    window_days: int = 7
    min_net_buy_days: int = 2
    min_foreign_flow_score: float = 0.0
    horizon_days: int = 20
    min_vwap_disc_pct: float | None = None
    trend: str | None = None
    min_flow_pct: float | None = None
    require_rsi: bool = False
    min_rsi: float | None = None
    max_rsi: float | None = None
    max_bb_width_pctile: float | None = None
    broker_quality: str | None = None
    simulate_exits: bool = False
    take_profit_pcts: tuple[float, ...] = ()
    stop_loss_pcts: tuple[float, ...] = ()
    max_hold_days: tuple[int, ...] = ()
    policy: AccumulationAuditPolicy = field(default_factory=AccumulationAuditPolicy)
