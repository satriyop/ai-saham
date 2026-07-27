"""
CLI command for multi-indicator snapshot view.

Layer: Adapter
"""

import json as _json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.indicator_display import (
    print_db_not_found_error,
    print_no_data_error,
    print_snapshot_summary,
    print_snapshot_table,
)
from src.application.use_case.aggregate_indicators_use_case import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def snapshot(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    sma_period: Annotated[int, typer.Option("--sma", help="SMA period (default: 20)", min=1)] = 20,
    ema_period: Annotated[int, typer.Option("--ema", help="EMA period (default: 20)", min=1)] = 20,
    rsi_period: Annotated[int, typer.Option("--rsi", help="RSI period (default: 14)", min=1)] = 14,
    days: Annotated[
        Optional[int],
        typer.Option("--days", "-d", help="Days of history to load", min=1),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="Path to SQLite database")] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Multi-indicator view: SMA, EMA, and RSI aligned by date.

    Shows only dates where all three indicators have values.
    Requires cached data (run `saham fetch market TICKER` first).

    Examples:
        saham indicator snapshot BBCA
        saham indicator snapshot BBRI --sma 50 --ema 50
        saham indicator snapshot TLKM --rsi 7 --days 180
    """
    cfg = load_app_config()
    resolved_days = days if days is not None else cfg.market.default_days
    resolved_db = db_path or Path(cfg.storage.db_path)
    resolved_fmt = fmt or cfg.analysis.format
    ticker_upper = ticker.upper()
    typer.echo(
        f"Loading {ticker_upper} · "
        f"SMA({sma_period})/EMA({ema_period})/RSI({rsi_period}) "
        f"from {resolved_db}..."
    )

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        use_case = AggregateIndicatorsUseCase(repository=repository)
        response = use_case.execute(
            AggregateIndicatorsRequest(
                ticker=ticker,
                sma_period=sma_period,
                ema_period=ema_period,
                rsi_period=rsi_period,
                days=resolved_days,
            )
        )

        if not response.has_values:
            typer.echo(
                f"[error] Insufficient data for {ticker_upper}."
                f" Have {response.candle_count} candles,"
                f" need at least {max(sma_period, ema_period, rsi_period)}.",
                err=True,
            )
            typer.echo(
                f"        Fix:   saham fetch market {ticker_upper} --days {resolved_days}", err=True
            )
            raise typer.Exit(1)

        if response.coverage_warning:
            typer.echo(f"[warning] {response.coverage_warning}", err=True)

        if resolved_fmt == "json":
            out = [
                {
                    "date": str(s.date),
                    f"sma_{sma_period}": float(s.sma),
                    f"ema_{ema_period}": float(s.ema),
                    f"rsi_{rsi_period}": float(s.rsi),
                }
                for s in response.snapshots
            ]
            typer.echo(_json.dumps(out, indent=2))
            return

        start, end = response.date_range or ("?", "?")
        typer.echo(f"\n{'=' * 60}")
        typer.echo(f" Indicator Snapshot  ·  {ticker_upper}  ·  {start} → {end}")
        typer.echo(
            f" SMA({response.sma_period}) / EMA({response.ema_period}) / RSI({response.rsi_period})"
            f"  ·  {response.snapshot_count} rows"
        )
        typer.echo(f"{'=' * 60}\n")

        print_snapshot_table(response)
        print_snapshot_summary(response)

    except typer.Exit:
        raise
    except FileNotFoundError:
        print_db_not_found_error(resolved_db, ticker_upper, days)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            print_no_data_error(ticker_upper, days)
        else:
            typer.echo(f"[error] Failed to compute indicators: {e}", err=True)
        raise typer.Exit(1)
