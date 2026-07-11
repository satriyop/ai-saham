"""
TP/SL/max-hold exit simulation for accumulation-audit replay records.

Layer: Application
Depends on: MarketDataRepository port
AI usage: None
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from src.application.dto.accumulation_audit import (
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AuditRecord,
    ExitSimulationStat,
)
from src.application.services.stats import average, pct_change, win_rate
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class _ExitOutcome:
    """Internal result for one simulated exit."""

    return_pct: float
    holding_days: int
    reason: str
    max_drawdown_pct: float


class AccumulationAuditExitSimulator:
    """Simulate TP/SL/max-hold exit rules across audited records."""

    def __init__(self, market_repository: MarketDataRepository) -> None:
        self._market_repo = market_repository

    def simulate(
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
    ) -> _ExitOutcome | None:
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


def _pct_change(value: Decimal, base: Decimal) -> float:
    return pct_change(value, base, precision=4)


def _avg(values: list[float | None]) -> float | None:
    return average(values, precision=4)


def _win_rate(values: list[float | None]) -> float | None:
    return win_rate(values, precision=2)


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
