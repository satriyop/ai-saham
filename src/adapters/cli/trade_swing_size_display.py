"""
Display helpers for saham trade size command.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.position_sizer import SizingResult


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
    # 1. Inputs Table
    inputs_table = compact_table(show_header=False)
    inputs_table.add_column("Parameter", style="bold cyan")
    inputs_table.add_column("Value")
    inputs_table.add_row("Capital", f"{capital:,.0f} IDR")
    inputs_table.add_row("Risk per trade", f"{risk_pct:.2f}% ({float(result.risk_amount):,.0f} IDR)")
    entry_src = "latest close" if not entry_price else "specified"
    inputs_table.add_row(f"Entry ({entry_src})", f"{float(entry_dec):,.0f}")
    inputs_table.add_row(f"ATR({atr_period})", f"{float(atr_value):.2f}")
    inputs_table.add_row("ATR multiplier", f"{float(result.atr_multiplier):.1f}x")
    inputs_table.add_row("Reward : Risk", f"{float(result.reward_risk_ratio):.1f}")

    # 2. Stop & Target Table
    levels_table = compact_table(show_header=False)
    levels_table.add_column("Parameter", style="bold cyan")
    levels_table.add_column("Value")
    levels_table.add_row("Stop Price", f"{float(result.stop_price):,.0f}")
    levels_table.add_row("Stop Distance", f"{float(result.stop_distance):,.0f} per share")
    levels_table.add_row("Stop %", f"{float(result.stop_pct):.2f}%")
    levels_table.add_row("Target Price", f"{float(result.target_price):,.0f}")
    levels_table.add_row("Target %", f"{float(result.target_pct):.2f}%")

    # 3. Position Details
    position_table = compact_table(show_header=False)
    position_table.add_column("Parameter", style="bold cyan")
    position_table.add_column("Value")

    if result.lots == 0:
        allocation_block = Text(
            f"INSUFFICIENT CAPITAL — cannot fill 1 lot.\n"
            f"Need at least {100 * float(entry_dec):,.0f} IDR for 1 lot "
            f"(stop = {float(result.stop_distance):.0f}/share).",
            style="bold red"
        )
    else:
        position_table.add_row("Raw shares", f"{int(result.risk_amount / result.stop_distance):,}")
        position_table.add_row("Round lots", f"{result.lots} lots ({result.shares:,} shares)")
        position_table.add_row("Position cost", f"{float(result.position_cost):,.0f} IDR ({float(result.capital_used_pct):.1f}% of capital)")
        actual_risk = Decimal(str(result.shares)) * result.stop_distance
        actual_reward = actual_risk * result.reward_risk_ratio
        position_table.add_row("Actual risk", f"{float(actual_risk):,.0f} IDR (vs target {float(result.risk_amount):,.0f})")
        position_table.add_row("Actual reward", f"{float(actual_reward):,.0f} IDR")
        allocation_block = position_table

    # Action Verdict Text
    if result.lots > 0:
        action_text = Text(
            f"ACTION: Buy {result.lots} lots at {float(entry_dec):,.0f}.  "
            f"Stop {float(result.stop_price):,.0f}.  "
            f"Target {float(result.target_price):,.0f}.",
            style="bold green"
        )
    else:
        action_text = Text("ACTION: No action (insufficient capital).", style="bold red")

    sections = [
        Text("Inputs", style="bold yellow"),
        inputs_table,
        Text("\nStop & Target Levels", style="bold yellow"),
        levels_table,
        Text("\nPosition Allocation", style="bold yellow"),
        allocation_block,
        Text("\nTrade Instruction", style="bold yellow"),
        action_text,
        Text("\nDISCLAIMER: Analysis only, not trading advice.", style="dim italic")
    ]

    console().print("")
    console().print(
        panel(
            Group(*sections),
            title=f"POSITION SIZE — {ticker} · {today}",
        )
    )
    console().print("")
