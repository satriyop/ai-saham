"""
Display helpers for swing position sizing CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer

from src.application.services.position_sizer import SizingResult


def sep(char: str = "=", width: int = 70) -> None:
    typer.echo(char * width)


def display_position_size(
    *,
    ticker: str,
    today: date,
    capital: int,
    risk_pct: float,
    entry_price: float | None,
    entry_dec: Decimal,
    atr_value: Decimal,
    atr_period: int,
    result: SizingResult,
) -> None:
    typer.echo("")
    sep("=")
    typer.echo(typer.style(
        f"POSITION SIZE — {ticker} · {today}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    sep("=")

    typer.echo("")
    typer.echo(typer.style("INPUTS", bold=True))
    typer.echo(
        f"  Capital            {capital:>18,} IDR"
    )
    typer.echo(
        f"  Risk per trade     {risk_pct:>17.2f} %  =  {float(result.risk_amount):>12,.0f} IDR"
    )
    entry_src = "latest close" if not entry_price else "specified"
    typer.echo(
        f"  Entry ({entry_src})   {float(entry_dec):>18,.0f}"
    )
    typer.echo(
        f"  ATR({atr_period:>2})           {float(atr_value):>18.2f}"
    )
    typer.echo(
        f"  ATR multiplier     {float(result.atr_multiplier):>18.1f}×"
    )
    typer.echo(
        f"  Reward : Risk      {float(result.reward_risk_ratio):>18.1f}"
    )

    typer.echo("")
    typer.echo(typer.style("STOP", bold=True))
    typer.echo(
        f"  Stop price         {float(result.stop_price):>18,.0f}"
    )
    typer.echo(
        f"  Stop distance      {float(result.stop_distance):>18,.0f}  per share"
    )
    typer.echo(
        f"  Stop %             {float(result.stop_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("TARGET", bold=True))
    typer.echo(
        f"  Target price       {float(result.target_price):>18,.0f}"
    )
    typer.echo(
        f"  Target %           {float(result.target_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("POSITION", bold=True))
    if result.lots == 0:
        typer.echo(typer.style(
            f"  INSUFFICIENT CAPITAL — cannot fill 1 lot.\n"
            f"  Need at least {100 * float(entry_dec):,.0f} IDR for 1 lot "
            f"(stop = {float(result.stop_distance):.0f}/share).",
            fg=typer.colors.RED,
        ))
    else:
        typer.echo(
            f"  Raw shares         {int(result.risk_amount / result.stop_distance):>18}"
        )
        typer.echo(
            f"  Round lots         {result.lots:>18}  lots = {result.shares:,} shares"
        )
        typer.echo(
            f"  Position cost      {float(result.position_cost):>18,.0f}  IDR  "
            f"({float(result.capital_used_pct):.1f}% of capital)"
        )
        actual_risk = Decimal(str(result.shares)) * result.stop_distance
        actual_reward = actual_risk * result.reward_risk_ratio
        typer.echo(
            f"  Actual risk        {float(actual_risk):>18,.0f}  IDR  "
            f"(vs target {float(result.risk_amount):,.0f})"
        )
        typer.echo(
            f"  Actual reward      {float(actual_reward):>18,.0f}  IDR"
        )

    typer.echo("")
    sep("=")
    if result.lots > 0:
        typer.echo(typer.style(
            f"ACTION: Buy {result.lots} lots at {float(entry_dec):,.0f}.  "
            f"Stop {float(result.stop_price):,.0f}.  "
            f"Target {float(result.target_price):,.0f}.",
            bold=True,
        ))
    sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")
