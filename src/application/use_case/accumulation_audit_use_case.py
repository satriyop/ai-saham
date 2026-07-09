"""
Historical audit for the foreign accumulation screener.

Replays accumulation signals over historical dates and measures forward
returns from local cached market and broker data.

Layer: Application
Depends on: Domain ports and accumulation screen use case
AI usage: None
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from src.application.services.stats import average, pct_change, win_rate
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository

SMART_MONEY_BROKERS = {"AK", "BK", "KZ", "ZP", "RX", "MS", "DB", "CS", "ML", "YU"}
NOISE_BROKERS = {"YP", "PD", "XL", "XC"}
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


class AccumulationAuditUseCase:
    """
    Replay the accumulation screener and measure forward performance.

    The use case is deterministic and offline: it reads local repositories only.
    It intentionally uses the current ticker universe supplied by the caller, so
    users should treat historical results as current-universe replay unless they
    provide historical universe snapshots.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        derived_feature_policy: AccumulationDerivedFeaturePolicy | None = None,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        self._screen = AccumulationScreenUseCase(
            broker_repository=broker_repository,
            market_repository=market_repository,
            derived_feature_policy=self._derived_features,
        )

    def execute(self, request: AccumulationAuditRequest) -> AccumulationAuditResponse:
        """Run the historical replay audit."""
        tickers = [t.upper().strip() for t in request.tickers if t.strip()]
        if not tickers:
            raise ValueError("At least one ticker is required")
        if request.start_date > request.end_date:
            raise ValueError("start_date must be on or before end_date")
        if request.horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        self._validate_policy(request.policy)
        if request.simulate_exits:
            self._validate_exit_simulation_request(request)

        replay_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        records: list[AuditRecord] = []
        skipped_no_forward_data = 0

        for signal_date in replay_dates:
            screen_response = self._screen.execute(
                AccumulationScreenRequest(
                    tickers=tickers,
                    window_days=request.window_days,
                    min_net_buy_days=request.min_net_buy_days,
                    min_foreign_flow_score=request.min_foreign_flow_score,
                    min_foreign_flow_score_enabled=True,
                    rsi_period=self._derived_features.rsi_period,
                    sma_period=self._derived_features.trend_sma_period,
                    as_of_date=signal_date,
                )
            )

            for candidate in screen_response.candidates:
                if not self._passes_filters(candidate, request, signal_date):
                    continue
                record = self._build_record(
                    candidate=candidate,
                    signal_date=signal_date,
                    horizon_days=request.horizon_days,
                    policy=request.policy,
                )
                if record is None:
                    skipped_no_forward_data += 1
                    continue
                records.append(record)

        warnings = [
            "Audit uses the supplied current universe; "
            "historical index membership is not reconstructed."
        ]

        return AccumulationAuditResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            window_days=request.window_days,
            total_replay_dates=len(replay_dates),
            total_tickers=len(tickers),
            total_records=len(records),
            skipped_no_forward_data=skipped_no_forward_data,
            records=records,
            group_stats=self._group_stats(records, request.policy),
            exit_simulations=(
                self._simulate_exits(records, request)
                if request.simulate_exits else []
            ),
            warnings=warnings,
        )

    def _validate_policy(self, policy: AccumulationAuditPolicy) -> None:
        """Validate tunable measurement policy values."""
        if any(horizon <= 0 for horizon in policy.forward_return_horizons):
            raise ValueError("forward_return_horizons must contain positive days")
        if policy.forward_fetch_buffer_days < 0:
            raise ValueError("forward_fetch_buffer_days cannot be negative")
        if policy.exit_fetch_buffer_days < 0:
            raise ValueError("exit_fetch_buffer_days cannot be negative")
        if policy.broker_quality_window_sessions <= 0:
            raise ValueError("broker_quality_window_sessions must be positive")
        if policy.same_day_exit_priority not in {"stop_first", "target_first"}:
            raise ValueError("same_day_exit_priority must be stop_first or target_first")

    def _validate_exit_simulation_request(
        self,
        request: AccumulationAuditRequest,
    ) -> None:
        """Validate exit simulation parameter grids."""
        if not request.take_profit_pcts:
            raise ValueError("take_profit_pcts is required when simulate_exits is enabled")
        if not request.stop_loss_pcts:
            raise ValueError("stop_loss_pcts is required when simulate_exits is enabled")
        if not request.max_hold_days:
            raise ValueError("max_hold_days is required when simulate_exits is enabled")
        if any(v <= 0 for v in request.take_profit_pcts):
            raise ValueError("take_profit_pcts must be positive")
        if any(v <= 0 for v in request.stop_loss_pcts):
            raise ValueError("stop_loss_pcts must be positive")
        if any(v <= 0 for v in request.max_hold_days):
            raise ValueError("max_hold_days must be positive")

    def _passes_filters(
        self,
        candidate: AccumulationCandidate,
        request: AccumulationAuditRequest,
        signal_date: date,
    ) -> bool:
        """Apply audit-only strict filters to a replayed candidate."""
        if request.min_vwap_disc_pct is not None:
            if candidate.vwap_discount_pct is None:
                return False
            if candidate.vwap_discount_pct < request.min_vwap_disc_pct:
                return False

        if request.trend is not None:
            if candidate.trend.upper() != request.trend.upper():
                return False

        if request.min_flow_pct is not None:
            if candidate.avg_flow_ratio is None:
                return False
            if candidate.avg_flow_ratio < request.min_flow_pct:
                return False

        if request.require_rsi and candidate.rsi is None:
            return False

        if request.max_rsi is not None:
            if candidate.rsi is None:
                return False
            if candidate.rsi > request.max_rsi:
                return False

        if request.min_rsi is not None:
            if candidate.rsi is None:
                return False
            if candidate.rsi < request.min_rsi:
                return False

        if request.max_bb_width_pctile is not None:
            if candidate.bb_width_pctile is None:
                return False
            if candidate.bb_width_pctile > request.max_bb_width_pctile:
                return False

        if request.broker_quality is not None:
            quality = self._broker_quality_bucket(
                ticker=candidate.ticker,
                signal_date=signal_date,
                window_sessions=request.policy.broker_quality_window_sessions,
            )
            if quality.lower() != request.broker_quality.lower():
                return False

        return True

    def _replay_dates(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """Build the union of available trading dates in the audit range."""
        dates: set[date] = set()
        for ticker in tickers:
            candles = self._market_repo.get_candles(
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
            dates.update(c.date for c in candles)
        return sorted(dates)

    def _build_record(
        self,
        candidate: AccumulationCandidate,
        signal_date: date,
        horizon_days: int,
        policy: AccumulationAuditPolicy,
    ) -> AuditRecord | None:
        """Convert a candidate into an audit record with forward returns."""
        forward = self._market_repo.get_candles(
            candidate.ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(
                days=horizon_days + policy.forward_fetch_buffer_days
            ),
        )
        forward = [c for c in forward if c.date > signal_date]
        if not forward:
            return None

        price = candidate.current_price
        if price <= Decimal("0"):
            return None

        def nth_return(n: int) -> float | None:
            if len(forward) < n:
                return None
            return _pct_change(forward[n - 1].close, price)

        horizon = forward[:horizon_days]
        max_upside = max((_pct_change(c.close, price) for c in horizon), default=None)
        max_drawdown = min((_pct_change(c.close, price) for c in horizon), default=None)
        forward_returns = {
            horizon: nth_return(horizon)
            for horizon in policy.forward_return_horizons
        }

        return AuditRecord(
            signal_date=signal_date,
            ticker=candidate.ticker,
            foreign_flow_score=candidate.foreign_flow_score,
            streak=candidate.consecutive_streak,
            net_buy_ratio=candidate.net_buy_ratio,
            total_net_value=candidate.total_net_value,
            flow_pct=candidate.avg_flow_ratio,
            vwap_disc_pct=candidate.vwap_discount_pct,
            rsi=candidate.rsi,
            bb_pctile=candidate.bb_width_pctile,
            trend=candidate.trend,
            broker_quality=self._broker_quality_bucket(
                ticker=candidate.ticker,
                signal_date=signal_date,
                window_sessions=policy.broker_quality_window_sessions,
            ),
            current_price=price,
            return_5d_pct=forward_returns.get(5),
            return_10d_pct=forward_returns.get(10),
            return_20d_pct=forward_returns.get(20),
            max_upside_pct=max_upside,
            max_drawdown_pct=max_drawdown,
            forward_returns_pct=forward_returns,
        )

    def _simulate_exits(
        self,
        records: list[AuditRecord],
        request: AccumulationAuditRequest,
    ) -> list[ExitSimulationStat]:
        """Run TP/SL/max-hold grids across all audited records."""
        stats: list[ExitSimulationStat] = []
        for take_profit in request.take_profit_pcts:
            for stop_loss in request.stop_loss_pcts:
                for max_hold in request.max_hold_days:
                    outcomes = [
                        outcome
                        for record in records
                        if (
                            outcome := self._simulate_exit(
                                record=record,
                                take_profit_pct=take_profit,
                                stop_loss_pct=stop_loss,
                                max_hold_days=max_hold,
                                policy=request.policy,
                            )
                        ) is not None
                    ]
                    stats.append(
                        _make_exit_simulation_stat(
                            take_profit_pct=take_profit,
                            stop_loss_pct=stop_loss,
                            max_hold_days=max_hold,
                            outcomes=outcomes,
                        )
                    )

        return sorted(
            stats,
            key=lambda s: (
                s.avg_return_pct if s.avg_return_pct is not None else -999,
                s.win_rate_pct if s.win_rate_pct is not None else -999,
            ),
            reverse=True,
        )

    def _simulate_exit(
        self,
        record: AuditRecord,
        take_profit_pct: float,
        stop_loss_pct: float,
        max_hold_days: int,
        policy: AccumulationAuditPolicy,
    ) -> "_ExitOutcome | None":
        """Simulate one deterministic exit path for one signal."""
        forward = self._market_repo.get_candles(
            record.ticker,
            start_date=record.signal_date + timedelta(days=1),
            end_date=record.signal_date + timedelta(
                days=max_hold_days + policy.exit_fetch_buffer_days
            ),
        )
        forward = [c for c in forward if c.date > record.signal_date]
        if not forward:
            return None

        entry = record.current_price
        target = entry * (Decimal("1") + Decimal(str(take_profit_pct)) / Decimal("100"))
        stop = entry * (Decimal("1") - Decimal(str(stop_loss_pct)) / Decimal("100"))
        max_drawdown = Decimal("0")

        for day_index, candle in enumerate(forward[:max_hold_days], start=1):
            drawdown = (candle.low - entry) / entry * Decimal("100")
            if drawdown < max_drawdown:
                max_drawdown = drawdown

            stop_hit = candle.low <= stop
            target_hit = candle.high >= target

            if stop_hit and (
                policy.same_day_exit_priority == "stop_first" or not target_hit
            ):
                return _ExitOutcome(
                    return_pct=_pct_change(stop, entry),
                    holding_days=day_index,
                    reason="stop",
                    max_drawdown_pct=round(float(max_drawdown), 4),
                )
            if target_hit:
                return _ExitOutcome(
                    return_pct=_pct_change(target, entry),
                    holding_days=day_index,
                    reason="target",
                    max_drawdown_pct=round(float(max_drawdown), 4),
                )
            if stop_hit:
                return _ExitOutcome(
                    return_pct=_pct_change(stop, entry),
                    holding_days=day_index,
                    reason="stop",
                    max_drawdown_pct=round(float(max_drawdown), 4),
                )

        exit_candle = forward[min(max_hold_days, len(forward)) - 1]
        return _ExitOutcome(
            return_pct=_pct_change(exit_candle.close, entry),
            holding_days=min(max_hold_days, len(forward)),
            reason="max_hold",
            max_drawdown_pct=round(float(max_drawdown), 4),
        )

    def _group_stats(
        self,
        records: list[AuditRecord],
        policy: AccumulationAuditPolicy,
    ) -> list[AuditGroupStat]:
        dimensions: dict[str, Callable[[AuditRecord], str]] = {
            "foreign_flow_score": lambda r: _range_bucket(
                r.foreign_flow_score,
                policy.buckets.foreign_flow_score,
            ),
            "streak": lambda r: _range_bucket(float(r.streak), policy.buckets.streak),
            "flow_pct": lambda r: _nullable_range_bucket(
                r.flow_pct, policy.buckets.flow_pct
            ),
            "vwap_disc_pct": lambda r: _nullable_range_bucket(
                r.vwap_disc_pct, policy.buckets.vwap_disc_pct
            ),
            "rsi": lambda r: _nullable_range_bucket(r.rsi, policy.buckets.rsi),
            "bb_pctile": lambda r: _nullable_range_bucket(
                r.bb_pctile, policy.buckets.bb_pctile
            ),
            "trend": lambda r: r.trend,
            "broker_quality": lambda r: r.broker_quality,
        }

        stats: list[AuditGroupStat] = []
        for dimension in policy.group_dimensions:
            bucket_fn = dimensions.get(dimension)
            if bucket_fn is None:
                continue
            buckets: dict[str, list[AuditRecord]] = {}
            for record in records:
                buckets.setdefault(bucket_fn(record), []).append(record)

            for bucket, rows in sorted(buckets.items()):
                stats.append(_make_group_stat(dimension, bucket, rows))

        return stats

    def _broker_quality_bucket(
        self,
        ticker: str,
        signal_date: date,
        window_sessions: int = 5,
    ) -> str:
        """Classify recent named top-broker flow available at signal date."""
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            end_date=signal_date,
        )
        detail_summaries = [
            summary for summary in summaries if summary.top_buyers or summary.top_sellers
        ][-window_sessions:]
        if not detail_summaries:
            return "no_detail"

        smart_flow = Decimal("0")
        noise_flow = Decimal("0")
        neutral_flow = Decimal("0")

        def add_flow(code: str, signed_value: Decimal) -> None:
            nonlocal smart_flow, noise_flow, neutral_flow
            code_upper = code.upper()
            if code_upper in SMART_MONEY_BROKERS:
                smart_flow += signed_value
            elif code_upper in NOISE_BROKERS:
                noise_flow += signed_value
            else:
                neutral_flow += signed_value

        for summary in detail_summaries:
            for tx in summary.top_buyers:
                if tx.net_value > Decimal("0"):
                    add_flow(tx.broker_code, tx.net_value)
            for tx in summary.top_sellers:
                if tx.net_value < Decimal("0"):
                    add_flow(tx.broker_code, tx.net_value)

        return _broker_quality_bucket_from_flows(
            smart_flow=smart_flow,
            noise_flow=noise_flow,
            neutral_flow=neutral_flow,
        )


@dataclass(frozen=True)
class _ExitOutcome:
    """Internal result for one simulated exit."""

    return_pct: float
    holding_days: int
    reason: str
    max_drawdown_pct: float


def _pct_change(value: Decimal, base: Decimal) -> float:
    return pct_change(value, base, precision=4)


def _avg(values: list[float | None]) -> float | None:
    return average(values, precision=4)


def _win_rate(values: list[float | None]) -> float | None:
    return win_rate(values, precision=2)


def _make_group_stat(
    dimension: str,
    bucket: str,
    records: list[AuditRecord],
) -> AuditGroupStat:
    return AuditGroupStat(
        dimension=dimension,
        bucket=bucket,
        count=len(records),
        avg_return_5d_pct=_avg([r.return_5d_pct for r in records]),
        avg_return_10d_pct=_avg([r.return_10d_pct for r in records]),
        avg_return_20d_pct=_avg([r.return_20d_pct for r in records]),
        win_rate_10d_pct=_win_rate([r.return_10d_pct for r in records]),
        avg_max_upside_pct=_avg([r.max_upside_pct for r in records]),
        avg_max_drawdown_pct=_avg([r.max_drawdown_pct for r in records]),
    )


def _make_exit_simulation_stat(
    take_profit_pct: float,
    stop_loss_pct: float,
    max_hold_days: int,
    outcomes: list[_ExitOutcome],
) -> ExitSimulationStat:
    count = len(outcomes)
    reasons = [o.reason for o in outcomes]

    def rate(reason: str) -> float | None:
        if count == 0:
            return None
        return round(sum(1 for r in reasons if r == reason) / count * 100, 2)

    return ExitSimulationStat(
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
        count=count,
        avg_return_pct=_avg([o.return_pct for o in outcomes]),
        win_rate_pct=_win_rate([o.return_pct for o in outcomes]),
        avg_holding_days=average([float(o.holding_days) for o in outcomes], precision=2),
        stop_rate_pct=rate("stop"),
        target_rate_pct=rate("target"),
        max_hold_rate_pct=rate("max_hold"),
        avg_max_drawdown_pct=_avg([o.max_drawdown_pct for o in outcomes]),
    )


def _broker_quality_bucket_from_flows(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> str:
    positive_total = sum(
        value
        for value in (smart_flow, noise_flow, neutral_flow)
        if value > Decimal("0")
    )
    negative_total = sum(
        abs(value)
        for value in (smart_flow, noise_flow, neutral_flow)
        if value < Decimal("0")
    )

    if positive_total == Decimal("0") and negative_total == Decimal("0"):
        return "no_detail"
    if negative_total > positive_total:
        if smart_flow < Decimal("0") and abs(smart_flow) >= abs(noise_flow):
            return "smart-"
        if noise_flow < Decimal("0"):
            return "noise-"
        return "mixed"
    if smart_flow > Decimal("0") and smart_flow >= noise_flow and smart_flow >= neutral_flow:
        return "smart+"
    if noise_flow > Decimal("0") and noise_flow >= smart_flow and noise_flow >= neutral_flow:
        return "noise+"
    return "mixed"


def _fmt_edge(value: float | int) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _range_bucket(value: float, edges: tuple[float | int, ...]) -> str:
    ordered = tuple(sorted(edges))
    if not ordered:
        return "all"
    if value < float(ordered[0]):
        return f"<{_fmt_edge(ordered[0])}"
    for lower, upper in zip(ordered, ordered[1:]):
        if value < float(upper):
            return f"{_fmt_edge(lower)}-{_fmt_edge(upper)}"
    return f"{_fmt_edge(ordered[-1])}+"


def _nullable_range_bucket(
    value: float | None,
    edges: tuple[float | int, ...],
) -> str:
    if value is None:
        return "missing"
    return _range_bucket(value, edges)


def _score_bucket(record: AuditRecord) -> str:
    if record.foreign_flow_score >= 58.3:
        return "58+"
    if record.foreign_flow_score >= 33.3:
        return "33-57"
    return "0-32"


def _streak_bucket(record: AuditRecord) -> str:
    if record.streak >= 5:
        return "5+"
    if record.streak >= 3:
        return "3-4"
    return "0-2"


def _flow_bucket(record: AuditRecord) -> str:
    value = record.flow_pct
    if value is None:
        return "missing"
    if value >= 15:
        return "15+"
    if value >= 5:
        return "5-15"
    return "<5"


def _vwap_bucket(record: AuditRecord) -> str:
    value = record.vwap_disc_pct
    if value is None:
        return "missing"
    if value >= 5:
        return "5+"
    if value >= 0:
        return "0-5"
    return "<0"


def _rsi_bucket(record: AuditRecord) -> str:
    value = record.rsi
    if value is None:
        return "missing"
    if value >= 60:
        return "60+"
    if value >= 45:
        return "45-60"
    if value >= 30:
        return "30-45"
    return "<30"


def _bb_bucket(record: AuditRecord) -> str:
    value = record.bb_pctile
    if value is None:
        return "missing"
    if value <= 0.20:
        return "<=20%"
    if value <= 0.40:
        return "20-40%"
    return ">40%"
