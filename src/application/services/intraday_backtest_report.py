"""Report builder and statistics aggregator for intraday backtesting results.

Layer: Application Service
"""

from decimal import Decimal

from src.application.dto.intraday_backtest import (
    IntradayBacktestRequest,
    IntradayBacktestResponse,
    IntradayBacktestTrade,
)
from src.application.services.stats import (
    average,
    max_drawdown_pct,
    profit_factor,
)


class IntradayBacktestReportBuilder:
    """Builds aggregate responses and breakdown reports from backtest run statistics."""

    def build_response(
        self,
        request: IntradayBacktestRequest,
        trades: list[IntradayBacktestTrade],
        final_equity: Decimal,
        equity_curve: list[Decimal],
        trading_days: int,
        days_with_trades: int,
        warnings: list[str],
    ) -> IntradayBacktestResponse:
        """Assemble a complete IntradayBacktestResponse with breakdowns."""
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]

        win_rate = round(len(wins) / len(trades) * 100, 1) if trades else None
        avg_ret = _avg([t.net_return_pct for t in trades])
        avg_win = _avg([t.net_return_pct for t in wins])
        avg_loss = _avg([t.net_return_pct for t in losses])
        pf = _profit_factor(trades)
        exp = _expectancy(trades)
        r_values = [t.r_multiple for t in trades if t.r_multiple is not None]
        avg_r = _avg(r_values) if r_values else None

        exit_counts: dict[str, int] = {}
        for t in trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        decision_counts: dict[str, int] = {}
        for t in trades:
            decision_counts[t.decision] = decision_counts.get(t.decision, 0) + 1

        total_return_pct = round(
            float((final_equity - request.capital) / request.capital * 100),
            4,
        )

        by_broker_backing = _breakdown_by(
            trades,
            lambda t: t.opening_broker_backing_tag or "none",
        )
        by_fvwap = _breakdown_by(
            trades,
            lambda t: (
                "positive"
                if (t.fvwap_discount_pct is not None and t.fvwap_discount_pct > 0)
                else "non-positive"
            ),
        )
        by_rsi = _breakdown_by(trades, lambda t: _rsi_bucket(t.rsi))
        by_ticker = _breakdown_by(trades, lambda t: t.ticker)
        by_ticker.sort(key=lambda r: -r["count"])
        by_ticker = by_ticker[:10]

        return IntradayBacktestResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            include_wait=request.include_wait,
            max_daily_positions=request.max_daily_positions,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            max_drawdown_pct=_max_drawdown(equity_curve),
            trade_count=len(trades),
            win_rate_pct=win_rate,
            avg_trade_return_pct=avg_ret,
            avg_winner_pct=avg_win,
            avg_loser_pct=avg_loss,
            profit_factor=pf,
            expectancy_pct=exp,
            avg_r_multiple=avg_r,
            exit_reason_counts=exit_counts,
            decisions=decision_counts,
            trading_days=trading_days,
            days_with_trades=days_with_trades,
            by_opening_broker_backing_tag=by_broker_backing,
            by_fvwap_sign=by_fvwap,
            by_rsi_bucket=by_rsi,
            by_ticker=by_ticker,
            trades=trades,
            warnings=warnings,
        )

    def empty_response(
        self,
        request: IntradayBacktestRequest,
        warnings: list[str],
    ) -> IntradayBacktestResponse:
        """Returns a zeroed/empty response with configured parameters."""
        return IntradayBacktestResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            include_wait=request.include_wait,
            max_daily_positions=request.max_daily_positions,
            final_equity=request.capital,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            trade_count=0,
            win_rate_pct=None,
            avg_trade_return_pct=None,
            avg_winner_pct=None,
            avg_loser_pct=None,
            profit_factor=None,
            expectancy_pct=None,
            avg_r_multiple=None,
            exit_reason_counts={},
            decisions={},
            trading_days=0,
            days_with_trades=0,
            by_opening_broker_backing_tag=[],
            by_fvwap_sign=[],
            by_rsi_bucket=[],
            by_ticker=[],
            trades=[],
            warnings=warnings,
        )


# ── Module Private Helpers ───────────────────────────────────────────────────


def _max_drawdown(equity_curve: list[Decimal]) -> float:
    return max_drawdown_pct(equity_curve, precision=4)


def _avg(values: list[float]) -> float | None:
    return average(values, precision=4)


def _profit_factor(trades: list[IntradayBacktestTrade]) -> float | None:
    return profit_factor((trade.pnl for trade in trades), precision=3)


def _expectancy(trades: list[IntradayBacktestTrade]) -> float | None:
    if not trades:
        return None
    wins = [t.net_return_pct for t in trades if t.pnl > 0]
    losses = [t.net_return_pct for t in trades if t.pnl < 0]
    if not wins and not losses:
        return None
    win_rate_val = len(wins) / len(trades)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return round(win_rate_val * avg_win + (1 - win_rate_val) * avg_loss, 4)


def _rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "rsi:missing"
    if rsi < 30:
        return "rsi:<30"
    if rsi <= 55:
        return "rsi:30-55"
    if rsi <= 70:
        return "rsi:55-70"
    return "rsi:>70"


def _breakdown_by(
    trades: list[IntradayBacktestTrade],
    key_fn,
    label_fn=None,
) -> list[dict]:
    """Generic breakdown: group trades by key, compute win_rate + avg_ret + total_pnl."""
    groups: dict[str, list[IntradayBacktestTrade]] = {}
    for t in trades:
        k = key_fn(t)
        groups.setdefault(k, []).append(t)

    rows = []
    for key, group in sorted(groups.items()):
        wins = [g for g in group if g.pnl > 0]
        rets = [g.net_return_pct for g in group]
        rows.append(
            {
                "label": label_fn(key) if label_fn else key,
                "count": len(group),
                "win_rate_pct": round(len(wins) / len(group) * 100, 1) if group else None,
                "avg_return_pct": round(sum(rets) / len(rets), 4) if rets else None,
                "total_pnl": sum(g.pnl for g in group),
            }
        )
    return rows
