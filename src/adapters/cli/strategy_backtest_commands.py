"""
CLI commands for strategy backtesting.

Layer: Adapter
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
    StrategyNotFoundError,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def backtest(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    strategy: Annotated[
        Optional[str],
        typer.Option("--strategy", "-S", help="Strategy name or path (e.g., 'momentum')"),
    ] = None,
    rules_file: Annotated[
        Optional[Path],
        typer.Option("--rules-file", "-r", help="Path to YAML rules file (backward-compatible)"),
    ] = None,
    start: Annotated[
        Optional[str], typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)")
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str], typer.Option("--end", "-e", help="End date (YYYY-MM-DD)")
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = APP_CFG.trading.capital,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show trade-by-trade output")
    ] = False,
    db_path: Annotated[
        Optional[Path], typer.Option("--db", help="Path to SQLite database")
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: table or json")
    ] = APP_CFG.analysis.format,
) -> None:
    """
    Backtest a strategy against historical data.

    Runs a deterministic simulation using rules from a strategy package or YAML file.
    Replays historical candles and applies rules per candle to generate signals.

    Strategy Resolution:
        --strategy resolves name as:
          1. ./NAME/strategy.yaml
          2. ./strategies/NAME/strategy.yaml

    Signal Mapping (customizable in YAML):
        LOW_RISK  → ENTER_LONG (buy)
        MODERATE  → HOLD
        HIGH_RISK → EXIT_LONG (sell)

    Examples:
        saham strategy backtest BBCA --strategy momentum
        saham strategy backtest BBCA -S ./strategies/momentum/strategy.yaml
        saham strategy backtest BBRI -S momentum --start 2024-01-01
        saham strategy backtest TLKM -S momentum --capital 50000000 --verbose
    """
    if not strategy and not rules_file:
        typer.echo("[error] Either --strategy or --rules-file is required.", err=True)
        typer.echo("        Fix:   saham strategy backtest BBCA --strategy momentum", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH

    start_date = None
    end_date = None
    try:
        if start:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        typer.echo("[error] Invalid date format. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(1)

    broker_repository = SQLiteBrokerRepository(resolved_db)

    if strategy:
        registry = create_indicator_registry(broker_repository=broker_repository)
        loader = StrategyLoader(registry=registry)
        try:
            resolved_rules_path = loader.resolve(strategy)
            strategy_display = strategy
        except StrategyNotFoundError as e:
            typer.echo(f"[error] {e}", err=True)
            raise typer.Exit(1)
    else:
        resolved_rules_path = rules_file  # type: ignore
        strategy_display = str(rules_file)

    typer.echo(f"Backtesting {ticker.upper()} with strategy '{strategy_display}'...")

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        registry = create_indicator_registry(
            broker_repository=broker_repository,
            market_repository=repository,
        )
        use_case = BacktestUseCase(repository=repository, registry=registry)
        response = use_case.execute(BacktestRequest(
            ticker=ticker,
            rules_file=resolved_rules_path,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(capital)),
        ))
        result = response.result

        if fmt == "json":
            import json as _json
            typer.echo(_json.dumps(result.to_dict(), indent=2))
            return

        typer.echo(f"\n{'='*52}")
        typer.echo(f" Backtest Results  ·  {result.ticker}  ·  {result.strategy_name}")
        typer.echo(f"{'='*52}\n")
        typer.echo(f"Period: {result.start_date} → {result.end_date}")

        typer.echo("\nPerformance")
        typer.echo(f"{'─'*40}")
        typer.echo(f"  Initial Capital:  {result.initial_capital:>18,.0f} IDR")
        typer.echo(f"  Final Capital:    {result.final_capital:>18,.0f} IDR")
        typer.echo(f"  Total Return:     {result.total_return_pct:>18.2f}%")
        typer.echo(f"  Max Drawdown:     {result.max_drawdown_pct:>18.2f}%")

        typer.echo("\nTrade Statistics")
        typer.echo(f"{'─'*40}")
        typer.echo(f"  Total Trades:     {result.trade_count:>18}")
        typer.echo(f"  Winning Trades:   {result.winning_trades:>18}")
        typer.echo(f"  Losing Trades:    {result.losing_trades:>18}")
        typer.echo(f"  Win Rate:         {result.win_rate:>18.2f}%")
        typer.echo(f"  Profit Factor:    {result.profit_factor:>18.2f}")
        if result.trades:
            typer.echo(f"  Avg Win:          {result.avg_win:>18,.0f} IDR")
            typer.echo(f"  Avg Loss:         {result.avg_loss:>18,.0f} IDR")

        if verbose and result.trades:
            typer.echo("\nTrade History")
            typer.echo("─" * 80)
            typer.echo(
                f"{'#':<4} {'Entry':<12} {'Exit':<12} {'Entry Price':>12}"
                f" {'Exit Price':>12} {'P&L':>14} {'%':>8}"
            )
            typer.echo("─" * 80)
            for i, trade in enumerate(result.trades, 1):
                sign = "+" if trade.pnl >= 0 else ""
                typer.echo(
                    f"{i:<4} {str(trade.entry_date):<12} {str(trade.exit_date):<12}"
                    f" {trade.entry_price:>12,.0f} {trade.exit_price:>12,.0f}"
                    f" {sign}{trade.pnl:>13,.0f} {trade.pnl_percent:>7.2f}%"
                )
            typer.echo("─" * 80)
            typer.echo(f"\nEntry Rules: {', '.join(set(t.entry_rule for t in result.trades))}")
            typer.echo(f"Exit Rules:  {', '.join(set(t.exit_rule for t in result.trades))}")

        typer.echo(f"\n{'='*52}")
        typer.echo("\nDISCLAIMER: Historical simulation only, not trading advice.")

    except StrategyNotFoundError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except RulesFileError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except RulesSchemaError as e:
        typer.echo(f"[error] Rules schema error: {e}", err=True)
        raise typer.Exit(1)
    except RulesValidationError as e:
        typer.echo(f"[error] Invalid rules: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"[error] Database not found at {resolved_db}.", err=True)
        typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
            typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)
        else:
            typer.echo(f"[error] Backtest failed: {e}", err=True)
        raise typer.Exit(1)
