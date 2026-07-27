"""
Display helpers for `saham view ticker financials`.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.adapters.cli.view_ticker_formatters import _fmt_idr
from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsResult,
)
from src.domain.value_objects.company_financial_period import CompanyFinancialPeriod


def display_ticker_financials(result: ViewTickerFinancialsResult) -> None:
    """Render financials deep-dive: status panel + period table when available."""
    console = Console()
    console.print("")

    title = f"[bold]{result.ticker} · {result.statement.title()} · {result.period_type}[/bold]"
    subtitle_bits = []
    if result.source:
        subtitle_bits.append(f"source={result.source}")
    if result.periods:
        subtitle_bits.append(f"{len(result.periods)} periods")
    subtitle = " · ".join(subtitle_bits) if subtitle_bits else None

    if result.status != "ok":
        body = Text(result.message or "No data.", style="yellow")
        console.print(
            Panel(body, title=title, subtitle=subtitle, border_style="yellow", expand=False)
        )
        if result.status == "empty" and result.fetch_hint:
            console.print(f"[dim]Hint: {result.fetch_hint}[/dim]")
        console.print("")
        return

    summary = Text()
    summary.append("Income statement (cached)  ", style="bold")
    latest = result.periods[0]
    summary.append(f"latest={latest.period_end.isoformat()}  ", style="cyan")
    if latest.currency:
        summary.append(f"currency={latest.currency}", style="dim")

    console.print(Panel(summary, title=title, subtitle=subtitle, border_style="cyan", expand=False))
    console.print("")
    console.print(_build_table(result.periods))
    console.print("")
    console.print(
        "[dim]Revenue definitions differ across providers; NI incl. NCI is the "
        "strongest cross-check line. Values in full currency units, abbreviated "
        "in display.[/dim]"
    )
    console.print("")


def _build_table(periods: tuple[CompanyFinancialPeriod, ...]) -> Table:
    table = Table(show_header=True, header_style="bold magenta", expand=False)
    table.add_column("Period", style="cyan", no_wrap=True)
    table.add_column("Revenue", justify="right")
    table.add_column("Net Income", justify="right")
    table.add_column("NI incl NCI", justify="right")
    table.add_column("Interest Inc", justify="right")
    table.add_column("Op. Income", justify="right")
    table.add_column("EPS basic", justify="right")
    table.add_column("EPS dil", justify="right")
    table.add_column("Src", style="dim", no_wrap=True)

    for p in periods:
        table.add_row(
            p.period_end.isoformat(),
            _fmt_idr(p.total_revenue),
            _fmt_idr(p.net_income),
            _fmt_idr(p.net_income_incl_nci),
            _fmt_idr(p.interest_income),
            _fmt_idr(p.operating_income),
            _fmt_eps(p.eps_basic),
            _fmt_eps(p.eps_diluted),
            p.source,
        )
    return table


def _fmt_eps(value: float | None) -> str:
    if value is None:
        return "\u2014"
    return f"{value:.2f}"
