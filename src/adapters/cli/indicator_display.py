"""
Display helpers for CLI indicator commands.

Layer: Adapter
"""

from decimal import Decimal
from pathlib import Path

import typer

from src.application.use_case.aggregate_indicators_use_case import AggregateIndicatorsResponse

VALID_FIELDS = ["open", "high", "low", "close"]


def rsi_signal(value: Decimal) -> str:
    if value > Decimal("70"):
        return "OVERBOUGHT"
    if value < Decimal("30"):
        return "OVERSOLD"
    return "NEUTRAL"


def print_no_data_error(ticker: str, days: int) -> None:
    typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days {days}", err=True)


def print_db_not_found_error(db_path: Path, ticker: str, days: int) -> None:
    typer.echo(f"[error] Database not found at {db_path}.", err=True)
    typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days {days}", err=True)


def validate_field(value: str) -> str:
    if value.lower() not in VALID_FIELDS:
        raise typer.BadParameter(
            f"Invalid field '{value}'. Must be one of: {', '.join(VALID_FIELDS)}"
        )
    return value.lower()


def print_compute_header(ticker: str, label: str, values: list, display_count: int = 0) -> None:
    typer.echo(f"\n{'='*52}")
    typer.echo(f" {label}  ·  {ticker}  ·  {values[0][0]} → {values[-1][0]}")
    typer.echo(f" {len(values)} values computed  (showing last {display_count or len(values)})")
    typer.echo(f"{'='*52}\n")


def print_compute_table(display_values: list, label: str, is_rsi: bool) -> None:
    if is_rsi:
        typer.echo(f"{'Date':<12} {label:>12}   Signal")
        typer.echo("─" * 36)
    else:
        typer.echo(f"{'Date':<12} {label:>14}")
        typer.echo("─" * 27)

    for dt, val in display_values:
        if is_rsi:
            sig = rsi_signal(val)
            marker = f"  ← {sig}" if sig != "NEUTRAL" else ""
            typer.echo(f"{dt!s:<12} {val:>12.2f}{marker}")
        else:
            typer.echo(f"{dt!s:<12} {val:>14.2f}")


def print_compute_summary(values: list, is_rsi: bool) -> None:
    all_vals = [v for _, v in values]
    all_dates = [d for d, _ in values]
    latest = all_vals[-1]
    peak_val = max(all_vals)
    trough_val = min(all_vals)
    peak_date = all_dates[all_vals.index(peak_val)]
    trough_date = all_dates[all_vals.index(trough_val)]

    typer.echo(f"\n{'─'*52}")
    typer.echo("Summary")
    typer.echo(f"{'─'*52}")
    if is_rsi:
        typer.echo(f"  Latest:   {latest:>10.2f}  ← {rsi_signal(latest)}")
    else:
        typer.echo(f"  Latest:   {latest:>10.2f}")
    typer.echo(f"  Peak:     {peak_val:>10.2f}  ({peak_date})")
    typer.echo(f"  Trough:   {trough_val:>10.2f}  ({trough_date})")


def print_snapshot_table(response: AggregateIndicatorsResponse) -> None:
    w = 13
    typer.echo(
        f"{'Date':<12} {'SMA':>{w}} {'EMA':>{w}} {'RSI':>8}   Signal"
    )
    typer.echo("─" * 60)

    for s in response.snapshots:
        sig = rsi_signal(s.rsi)
        marker = f"  ← {sig}" if sig != "NEUTRAL" else ""
        typer.echo(
            f"{s.date!s:<12} {s.sma:>{w},.2f} {s.ema:>{w},.2f} {s.rsi:>8.2f}{marker}"
        )


def print_snapshot_summary(response: AggregateIndicatorsResponse) -> None:
    if not response.snapshots:
        return
    sma_vals = [s.sma for s in response.snapshots]
    ema_vals = [s.ema for s in response.snapshots]
    rsi_vals = [s.rsi for s in response.snapshots]
    latest = response.snapshots[-1]

    typer.echo(f"\n{'─'*60}")
    typer.echo("Summary (latest)")
    typer.echo(f"{'─'*60}")
    typer.echo(f"  SMA({response.sma_period}):  {latest.sma:>12,.2f}  Range [{min(sma_vals):,.2f} – {max(sma_vals):,.2f}]")
    typer.echo(f"  EMA({response.ema_period}):  {latest.ema:>12,.2f}  Range [{min(ema_vals):,.2f} – {max(ema_vals):,.2f}]")
    rsi_sig = rsi_signal(latest.rsi)
    typer.echo(
        f"  RSI({response.rsi_period}):  {latest.rsi:>12.2f}  Range [{min(rsi_vals):.2f} – {max(rsi_vals):.2f}]"
        f"  ← {rsi_sig}"
    )



