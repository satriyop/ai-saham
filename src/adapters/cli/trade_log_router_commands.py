"""
CLI command for unified trade journal logging.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_accum_commands import (
    DEFAULT_ACCUM_JOURNAL_PATH,
    DEFAULT_DB_PATH,
    FOREIGN_BOUNCE_SETUP,
    _accumulation_log_impl,
)
from src.adapters.cli.trade_intraday_commands import (
    DEFAULT_CONFIRMATION_JOURNAL_PATH,
    DEFAULT_CONFIRMATION_PATH,
    _confirm_log_impl,
)


def trade_log(
    trade_type: Annotated[
        str,
        typer.Option("--type", help="Trade type: swing or intraday"),
    ],
    # swing options
    ticker: Annotated[
        Optional[str],
        typer.Option("--ticker", "-t", help="Ticker to log (swing only)"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in sessions (swing only)", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (swing only)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record setup match, failed gates, trade plan (swing only)",
        ),
    ] = False,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup name"),
    ] = FOREIGN_BOUNCE_SETUP,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label (swing only)"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "IHSG",
    # intraday options
    confirmation: Annotated[
        Optional[Path],
        typer.Option("--confirmation", help="Confirmation sidecar JSON path (intraday only)"),
    ] = None,
    # shared
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Override journal file path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log a paper-trade decision to the unified trade journal (trades.jsonl).

    Writes to the type-specific CSV journal and to journals/trades.jsonl.
    Idempotent: re-running for the same key never duplicates rows.

    Examples:
        saham trade log --type swing --ticker BBRI --window 7
        saham trade log --type swing --ticker BBCA --from-analysis --with-regime
        saham trade log --type intraday
        saham trade log --type intraday --confirmation journals/.last-confirmation.json
    """
    if trade_type == "swing":
        if ticker is None:
            typer.echo("--ticker is required for --type swing", err=True)
            raise typer.Exit(1)
        _accumulation_log_impl(
            ticker=ticker,
            window=window,
            entry_price=entry_price,
            from_analysis=from_analysis,
            setup=setup,
            with_regime=with_regime,
            regime_universe=regime_universe,
            benchmark=benchmark,
            journal_path=journal or DEFAULT_ACCUM_JOURNAL_PATH,
            db_path=db_path or DEFAULT_DB_PATH,
        )
    elif trade_type == "intraday":
        _confirm_log_impl(
            confirmation_path=confirmation or DEFAULT_CONFIRMATION_PATH,
            journal_path=journal or DEFAULT_CONFIRMATION_JOURNAL_PATH,
        )
    else:
        typer.echo(
            f"Unknown --type '{trade_type}'. Valid values: swing, intraday",
            err=True,
        )
        raise typer.Exit(1)
