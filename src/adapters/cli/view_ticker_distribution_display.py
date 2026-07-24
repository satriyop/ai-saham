"""
Display helpers for broker distribution CLI output.

Layer: Adapter (display-only, no provider/repository/config/db construction)
"""

from __future__ import annotations

import typer

from src.domain.value_objects.broker_distribution import BrokerDistributionSnapshot


def _fmt_idr(amount: int) -> str:
    """Format IDR amount as compact string (e.g. 510.5B, 88.4M)."""
    abs_amt = abs(amount)
    if abs_amt >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}T"
    if abs_amt >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if abs_amt >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    return f"{amount:,}"


def _broker_label(code: str, btype: str) -> str:
    tag = "A" if btype.lower() == "asing" else ("G" if btype.lower() == "pemerintah" else "L")
    return f"{code}[{tag}]"


def display_broker_distribution(snapshot: BrokerDistributionSnapshot) -> None:
    """Render ASCII cross-broker distribution table."""
    acc_signal = ""
    if snapshot.foreign_buying_from_domestic:
        acc_signal = typer.style(
            "  ★ Foreign accumulating from domestic (smart money signal)",
            fg=typer.colors.GREEN,
        )
    elif snapshot.net_foreign_buyer_dominance:
        acc_signal = typer.style("  ● Foreign brokers dominate buy side", fg=typer.colors.CYAN)

    typer.echo(f"\n  {snapshot.ticker} — Broker Distribution  ({snapshot.date})")
    typer.echo(f"  {'─' * 64}")
    if acc_signal:
        typer.echo(acc_signal)

    def _render_side(entries, side_label: str, arrow: str) -> None:
        if not entries:
            return
        typer.echo(f"\n  {side_label}")
        typer.echo(f"  {'─' * 60}")
        for entry in entries[:5]:
            total_str = _fmt_idr(entry.amount_idr)
            label = _broker_label(entry.broker_code, entry.broker_type)
            color = typer.colors.GREEN if side_label.startswith("TOP BUYERS") else typer.colors.RED
            header = typer.style(f"  {label:<10} {total_str:>8}", fg=color)
            typer.echo(header)
            for cp in entry.counterparties[:4]:
                cp_label = _broker_label(cp.broker_code, cp.broker_type)
                pct = cp.amount_idr / entry.amount_idr * 100 if entry.amount_idr else 0
                is_lokal = cp.broker_type.lower() == "lokal"
                cp_color = typer.colors.YELLOW if is_lokal else typer.colors.BRIGHT_BLACK
                typer.echo(
                    typer.style(
                        f"    {arrow} {cp_label:<10} {_fmt_idr(cp.amount_idr):>8}  ({pct:.0f}%)",
                        fg=cp_color,
                    )
                )

    _render_side(snapshot.top_buyers, "TOP BUYERS  (bought FROM →)", "←")
    _render_side(snapshot.top_sellers, "TOP SELLERS (sold TO →)", "→")
    typer.echo("")
