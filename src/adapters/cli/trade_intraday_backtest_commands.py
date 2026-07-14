"""
CLI commands for intraday proxy simulation.

Layer: Adapter
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def intraday_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached'"),
    ] = None,
    start: Annotated[
        Optional[str],
        typer.Option("--start", help="Simulation start date YYYY-MM-DD"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Simulation end date YYYY-MM-DD"),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = None,
    risk_pct: Annotated[
        Optional[float],
        typer.Option("--risk-pct", help="% of capital at risk per trade", min=0.01),
    ] = None,
    max_daily_positions: Annotated[
        int,
        typer.Option("--max-daily-positions", help="Max simultaneous trades per day", min=1),
    ] = 3,
    max_stop: Annotated[
        Optional[float],
        typer.Option(
            "--max-stop",
            help="Max allowed stop distance; defaults to pre-open config",
            min=0.005,
        ),
    ] = None,
    cost_bps: Annotated[
        Optional[float],
        typer.Option("--cost-bps", help="Transaction cost in basis points per side", min=0),
    ] = None,
    include_wait: Annotated[
        bool,
        typer.Option("--include-wait/--no-include-wait", help="Treat WAIT decisions as ENTER"),
    ] = False,
    atr_mult: Annotated[
        Optional[float],
        typer.Option(
            "--atr-mult",
            help="ATR multiplier for stop distance; defaults to pre-open config",
            min=0.1,
        ),
    ] = None,
    rsi_overbought: Annotated[
        Optional[float],
        typer.Option(
            "--rsi-overbought",
            help="RSI threshold for BEARISH classification; defaults to pre-open config",
        ),
    ] = None,
    iev_top_n: Annotated[
        int,
        typer.Option("--iev-top-n", help="IEV snapshots filter top-N movers limit", min=1),
    ] = 5,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to display", min=0),
    ] = 20,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Daily-OHLC proxy simulation of the intraday pre-open workflow.

    This is not an exact intraday replay. It uses candle.open as the entry
    proxy, same-day high/low/close for exits, and applies saved IEV snapshots
    only on dates where they exist.
    """
    cfg = load_app_config()
    start = start or cfg.backtest.start_date
    capital = capital if capital is not None else cfg.trading.capital
    risk_pct = risk_pct if risk_pct is not None else cfg.swing.risk_pct
    cost_bps = cost_bps if cost_bps is not None else cfg.backtest.cost_bps
    output_format = output_format or cfg.analysis.format

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as exc:
        typer.echo(f"Error: invalid date format — {exc}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or Path(cfg.storage.db_path)
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
        )
    except (UniverseNotFoundError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    po_config = load_pre_open_screen_config()
    resolved_max_stop = Decimal(str(max_stop)) if max_stop is not None else po_config.max_stop_pct
    resolved_atr_mult = (
        Decimal(str(atr_mult)) if atr_mult is not None else po_config.atr_multiplier
    )
    resolved_rsi_overbought = (
        Decimal(str(rsi_overbought))
        if rsi_overbought is not None
        else po_config.rsi_overbought_threshold
    )

    typer.echo(
        f"Intraday proxy simulation: {len(ticker_list)} tickers | "
        f"{start_date} to {end_date} | "
        f"max_daily={max_daily_positions} | "
        f"include_wait={include_wait}",
        err=True,
    )

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
    iev_repo = SQLiteIEVRepository(resolved_db)
    coverage = iev_repo.get_coverage()
    if coverage["total_dates"] > 0:
        typer.echo(
            f"IEV snapshots: {coverage['total_dates']} days "
            f"({coverage['first_date']} → {coverage['last_date']}) — "
            f"top-{iev_top_n} filter will be applied where available.",
            err=True,
        )
    else:
        typer.echo(
            "No IEV snapshots found. Screening full universe each day. "
            "Run 'saham fetch iev' at 08:50 WIB to start collecting.",
            err=True,
        )
        iev_repo = None

    use_case = IntradayBacktestUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        indicator_registry=registry,
        iev_repository=iev_repo,
    )

    try:
        response = use_case.execute(IntradayBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_daily_positions=max_daily_positions,
            max_stop_pct=resolved_max_stop,
            cost_bps=Decimal(str(cost_bps)),
            include_wait=include_wait,
            atr_multiplier=resolved_atr_mult,
            rsi_overbought_threshold=resolved_rsi_overbought,
            atr_range_cap_min=po_config.atr_range_cap_min,
            atr_range_cap_max=po_config.atr_range_cap_max,
            broker_backing_window_days=po_config.broker_backing_window_days,
            broker_backing_threshold=po_config.broker_backing_threshold,
            fvwap_period=po_config.fvwap_period,
            history_days=po_config.history_days,
            iev_top_n=iev_top_n,
        ))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        import json as _json
        typer.echo(_json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "intraday_proxy_simulation",
                "start_date": response.start_date.isoformat(),
                "end_date": response.end_date.isoformat(),
                "initial_capital": str(response.initial_capital),
                "cost_bps": str(response.cost_bps),
                "include_wait": response.include_wait,
                "final_equity": str(response.final_equity),
                "total_return_pct": response.total_return_pct,
                "max_drawdown_pct": response.max_drawdown_pct,
                "trade_count": response.trade_count,
                "win_rate_pct": response.win_rate_pct,
                "avg_trade_return_pct": response.avg_trade_return_pct,
                "profit_factor": response.profit_factor,
                "expectancy_pct": response.expectancy_pct,
                "avg_r_multiple": response.avg_r_multiple,
                "exit_reason_counts": response.exit_reason_counts,
                "decisions": response.decisions,
                "by_opening_broker_backing_tag": [
                    {**r, "total_pnl": str(r["total_pnl"])}
                    for r in response.by_opening_broker_backing_tag
                ],
                "by_fvwap_sign": [
                    {**r, "total_pnl": str(r["total_pnl"])}
                    for r in response.by_fvwap_sign
                ],
                "by_rsi_bucket": [
                    {**r, "total_pnl": str(r["total_pnl"])}
                    for r in response.by_rsi_bucket
                ],
                "by_ticker": [
                    {**r, "total_pnl": str(r["total_pnl"])}
                    for r in response.by_ticker
                ],
                "trades": [t.to_dict() for t in response.trades],
                "warnings": response.warnings,
            },
            indent=2,
            default=str,
        ))
        return

    from src.adapters.cli.trade_intraday_backtest_display import display_intraday_backtest
    display_intraday_backtest(response, show_trades=show_trades)
