"""
CLI: saham backtest portfolio swing

Offline portfolio walk-forward for a named swing setup (capital, risk, slots, costs).
Not live TradeSetup (`plan swing`). Not corpus (`research`). Not policy apply.

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.backtest_portfolio_runner import _run_swing_backtest
from src.adapters.cli.backtest_portfolio_display import display_swing_backtest
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestResponse,
)
from src.infrastructure.config.app_config import load_app_config


def _swing_backtest_payload(response: SwingBacktestResponse) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "swing_backtest",
        "setup": response.setup,
        "start_date": response.start_date.isoformat(),
        "end_date": response.end_date.isoformat(),
        "initial_capital": str(response.initial_capital),
        "cost_bps": str(response.cost_bps),
        "final_equity": str(response.final_equity),
        "total_return_pct": response.total_return_pct,
        "max_drawdown_pct": response.max_drawdown_pct,
        "trade_count": response.trade_count,
        "win_rate_pct": response.win_rate_pct,
        "avg_trade_return_pct": response.avg_trade_return_pct,
        "profit_factor": response.profit_factor,
        "exposure_pct": response.exposure_pct,
        "skipped_no_cash": response.skipped_no_cash,
        "skipped_duplicate": response.skipped_duplicate,
        "skipped_no_forward_data": response.skipped_no_forward_data,
        "skipped_by_regime": response.skipped_by_regime,
        "warnings": response.warnings,
        "regime_stats": [stat.to_dict() for stat in response.regime_stats],
        "regime_by_date": {
            key.isoformat(): value.to_dict()
            for key, value in response.regime_by_date.items()
        },
        "attribution_summary": response.attribution_summary.to_dict(),
        "trades": [trade.to_dict() for trade in response.trades],
        "candidate_observations": [
            observation.to_dict()
            for observation in response.candidate_observations
        ],
        "equity_curve": [point.to_dict() for point in response.equity_curve],
    }


def swing_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        Optional[str],
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = None,
    risk_pct: Annotated[
        Optional[float],
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = None,
    max_positions: Annotated[
        Optional[int],
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = None,
    take_profit: Annotated[
        Optional[float],
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = None,
    stop_loss: Annotated[
        Optional[float],
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = None,
    max_hold: Annotated[
        Optional[int],
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = None,
    cost_bps: Annotated[
        Optional[float],
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = None,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group trades by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        Optional[str],
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = None,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to print", min=0),
    ] = 20,
    with_attribution: Annotated[
        bool,
        typer.Option(
            "--with-attribution",
            help="Show deterministic grouped attribution summary for tuning",
        ),
    ] = False,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Offline portfolio walk-forward for a named swing setup.

    Simulates multi-position trading with capital, risk %, max positions, and costs.
    Equity curve and trades — not a live `plan swing` decision.
    After sim: policy lifecycle is `saham policy accum tune|review|validate|apply`.
    """
    cfg = load_app_config()
    start = start or cfg.backtest.start_date
    benchmark = benchmark or cfg.analysis.benchmark
    output_format = output_format or cfg.analysis.format

    from src.adapters.cli.backtest_portfolio_runner import load_swing_backtest_runner_config
    runner_config = load_swing_backtest_runner_config()

    resolved_capital = (
        capital if capital is not None else runner_config.backtest_config.capital
    )
    resolved_risk_pct = (
        risk_pct if risk_pct is not None else runner_config.backtest_config.risk_pct
    )
    resolved_max_positions = (
        max_positions if max_positions is not None
        else runner_config.backtest_config.max_positions
    )
    resolved_take_profit = (
        take_profit if take_profit is not None
        else runner_config.backtest_config.take_profit_pct
    )
    resolved_stop_loss = (
        stop_loss if stop_loss is not None
        else runner_config.backtest_config.stop_loss_pct
    )
    resolved_max_hold = (
        max_hold if max_hold is not None else runner_config.backtest_config.max_hold_days
    )
    resolved_cost_bps = (
        cost_bps if cost_bps is not None else runner_config.backtest_config.cost_bps
    )

    response = _run_swing_backtest(
        tickers=tickers,
        universe=universe,
        setup=setup,
        start=start,
        end=end,
        capital=resolved_capital,
        risk_pct=resolved_risk_pct,
        max_positions=resolved_max_positions,
        take_profit=resolved_take_profit,
        stop_loss=resolved_stop_loss,
        max_hold=resolved_max_hold,
        cost_bps=resolved_cost_bps,
        with_regime=with_regime,
        allow_regimes=allow_regimes,
        benchmark=benchmark,
        db_path=db_path,
        announce=output_format != "json",
        config=runner_config,
    )

    if output_format == "json":
        payload = _swing_backtest_payload(response)
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_backtest(
        response,
        show_trades=show_trades,
        show_attribution=with_attribution,
    )
