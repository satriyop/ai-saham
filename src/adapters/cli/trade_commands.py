"""
CLI commands for active trading workflows.

Commands (all under `saham trade`):
  saham trade confirm             — opening confirmation gate
  saham trade log --type swing    — log swing accumulation candidate
  saham trade log --type intraday — log intraday confirmation decisions
  saham trade review intraday     — review intraday confirmation journal
  saham trade review swing        — review swing accumulation journal
  saham trade outcome             — record intraday outcome
  saham trade size                — ATR-based swing position sizing
  saham trade backtest-swing      — swing workflow walk-forward backtest
  saham trade backtest-intraday   — intraday workflow walk-forward backtest
  saham trade migrate-journal     — one-time migration of CSV journals to trades.jsonl

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.infrastructure.config.app_config import APP_CFG

from src.adapters.cli.accumulation_commands import (
    DEFAULT_ACCUM_JOURNAL_PATH,
    DEFAULT_DB_PATH,
    FOREIGN_BOUNCE_PRESET,
    _accumulation_log_impl,
    accumulation_review,
)
from src.adapters.cli.trade_swing_commands import size, swing_backtest
from src.adapters.cli.trade_intraday_commands import (
    confirm_open,
    confirm_outcome,
    confirm_review,
    intraday_backtest,
)
from src.adapters.cli.intraday_workflow_commands import (
    DEFAULT_CONFIRMATION_JOURNAL_PATH,
    DEFAULT_CONFIRMATION_PATH,
    _confirm_log_impl,
)

trade_app = typer.Typer(
    name="trade",
    help="Paper trading workspace — confirmation, journals, sizing, and workflow backtests.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

trade_review_app = typer.Typer(
    name="review",
    help="Review paper-trade journals by workflow.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_review_app.command("intraday")(confirm_review)
trade_review_app.command("swing")(accumulation_review)

trade_app.command("confirm")(confirm_open)
trade_app.add_typer(trade_review_app, name="review")
trade_app.command("outcome")(confirm_outcome)
trade_app.command("size")(size)
trade_app.command("backtest-swing")(swing_backtest)
trade_app.command("backtest-intraday")(intraday_backtest)


@trade_app.command("log")
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
        typer.Option("--from-analysis", help="Record preset, failed gates, trade plan (swing only)"),
    ] = False,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset name"),
    ] = FOREIGN_BOUNCE_PRESET,
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
    ] = "^JKSE",
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
            preset=preset,
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


@trade_app.command("migrate-journal")
def trade_migrate_journal(
    trades_journal: Annotated[
        Optional[Path],
        typer.Option("--output", help="Output trades.jsonl path"),
    ] = None,
    accum_csv: Annotated[
        Optional[Path],
        typer.Option("--accum-csv", help="Source accumulation CSV"),
    ] = None,
    intraday_csv: Annotated[
        Optional[Path],
        typer.Option("--intraday-csv", help="Source intraday confirmations CSV"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print records without writing"),
    ] = False,
) -> None:
    """
    One-time migration: convert existing CSV journals to journals/trades.jsonl.

    Reads journals/accumulation.csv and journals/intraday-confirmations.csv,
    converts each row to the unified schema, and appends to trades.jsonl.
    Idempotent — safe to run multiple times.
    """
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        accumulation_entry_to_record,
        intraday_entry_to_record,
    )

    output_path = trades_journal or Path(APP_CFG.storage.trade_journal)
    accum_path = accum_csv or DEFAULT_ACCUM_JOURNAL_PATH
    intraday_path = intraday_csv or DEFAULT_CONFIRMATION_JOURNAL_PATH

    swing_entries = AccumulationJournalCsvWriter(accum_path).read_all() if accum_path.exists() else []
    intraday_entries = IntradayConfirmationCsvStore(intraday_path).read_all() if intraday_path.exists() else []

    records = [accumulation_entry_to_record(e) for e in swing_entries] + \
              [intraday_entry_to_record(e) for e in intraday_entries]

    if dry_run:
        import json
        for r in records:
            typer.echo(json.dumps(r))
        typer.echo(f"\n{len(records)} record(s) would be written to {output_path}")
        return

    store = TradeJournalJsonlWriter(output_path)
    written = sum(1 for r in records if store.append(r))
    skipped = len(records) - written
    typer.echo(
        f"Migration complete → {output_path}\n"
        f"  Swing:    {len(swing_entries)} source rows\n"
        f"  Intraday: {len(intraday_entries)} source rows\n"
        f"  Written:  {written}  Skipped (duplicates): {skipped}"
    )
