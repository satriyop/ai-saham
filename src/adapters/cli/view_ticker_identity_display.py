"""
Identity, freshness, and company profile panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import panel
from src.adapters.cli.view_ticker_formatters import _not_cached
from src.adapters.cli.view_ticker_status import FreshnessItem, format_freshness_lines


def _identity_panel(ticker: str, notation, *, empty_hint: str | None = None) -> object:
    if notation is None:
        return panel(_not_cached(hint=empty_hint), title=f"[bold]{ticker}[/bold]")

    parts: list[str] = []
    if notation.listing_board:
        parts.append(notation.listing_board)
    if notation.sector:
        parts.append(notation.sector)
    if notation.sub_sector and notation.sub_sector != notation.sector:
        parts.append(notation.sub_sector)

    status_text = "\u2713 Tradeable" if notation.tradeable else "\u2717 Not Tradeable"
    status_style = "green" if notation.tradeable else "red"

    lines: list[Text] = []
    if parts:
        lines.append(Text("  " + " \u00b7 ".join(parts), style="dim"))
    lines.append(Text(f"  {status_text}", style=status_style))
    if notation.codes_label and notation.codes_label != "-":
        lines.append(Text(f"  Notations: {notation.codes_label}", style="yellow"))
    if notation.suspend_info:
        lines.append(Text(f"  Suspend: {notation.suspend_info}", style="red"))
    if notation.fetched_at:
        lines.append(Text(f"  Fetched: {notation.fetched_at.date()}", style="dim"))

    title = f"[bold]{ticker}[/bold]"
    if notation.listing_board:
        title += f"  [dim]{notation.listing_board}[/dim]"
    return panel(Group(*lines), title=title)


def _freshness_panel(
    ticker: str,
    items: list[FreshnessItem],
    *,
    as_of: date | None = None,
) -> object:
    """Compact cache-completeness strip for the dashboard header."""
    lines = format_freshness_lines(ticker, items, as_of=as_of)
    body = Group(*[Text(f"  {line}", style="dim" if i else "default") for i, line in enumerate(lines)])
    return panel(body, title="Data Freshness")


def _profile_panel(prof, *, empty_hint: str | None = None) -> object:
    if prof is None:
        return panel(_not_cached(hint=empty_hint), title="Company Profile")

    lines: list[Text] = []

    ipo_parts: list[str] = []
    if prof.ipo_date:
        ipo_parts.append(f"IPO {prof.ipo_date}")
    if prof.ipo_price:
        ipo_parts.append(f"@ Rp{prof.ipo_price:,}")
    if prof.ipo_amount:
        ipo_parts.append(f"({prof.ipo_amount} raised)")
    if ipo_parts:
        lines.append(Text("  " + "  ".join(ipo_parts), style="default"))

    if prof.website:
        lines.append(Text(f"  Web    {prof.website}", style="default"))
    if prof.email:
        lines.append(Text(f"  Email  {prof.email}", style="default"))

    if prof.background:
        bg = prof.background[:220]
        if len(prof.background) > 220:
            bg += "\u2026"
        lines.append(Text("  ─────────────────────────────────────────", style="dim"))
        lines.append(Text(f"  {bg}", style="dim"))

    if prof.fetched_at:
        lines.append(Text(f"  Fetched: {prof.fetched_at.date()}", style="dim"))

    return panel(Group(*lines), title="Company Profile")
