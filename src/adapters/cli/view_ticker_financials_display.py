"""
Display helpers for `saham view ticker financials`.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.adapters.cli.view_ticker_formatters import _fmt_idr
from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsResult,
)
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialStatementKind,
)

# (header, formatter) — kind-specific columns only.
_Column = tuple[str, Callable[[CompanyFinancialPeriod], str]]

_COLUMNS: dict[FinancialStatementKind, tuple[_Column, ...]] = {
    "income": (
        ("Revenue", lambda p: _fmt_idr(p.total_revenue)),
        ("Net Income", lambda p: _fmt_idr(p.net_income)),
        ("NI incl NCI", lambda p: _fmt_idr(p.net_income_incl_nci)),
        ("Interest Inc", lambda p: _fmt_idr(p.interest_income)),
        ("Op. Income", lambda p: _fmt_idr(p.operating_income)),
        ("EPS basic", lambda p: _fmt_eps(p.eps_basic)),
        ("EPS dil", lambda p: _fmt_eps(p.eps_diluted)),
    ),
    "balance": (
        ("Total Assets", lambda p: _fmt_idr(p.total_assets)),
        ("Total Liab.", lambda p: _fmt_idr(p.total_liabilities)),
        ("Equity", lambda p: _fmt_idr(p.stockholders_equity)),
        ("Cash", lambda p: _fmt_idr(p.cash_and_equivalents)),
        ("Total Debt", lambda p: _fmt_idr(p.total_debt)),
    ),
    "cashflow": (
        ("Op. CF", lambda p: _fmt_idr(p.operating_cash_flow)),
        ("Inv. CF", lambda p: _fmt_idr(p.investing_cash_flow)),
        ("Fin. CF", lambda p: _fmt_idr(p.financing_cash_flow)),
        ("Free CF", lambda p: _fmt_idr(p.free_cash_flow)),
        ("CapEx", lambda p: _fmt_idr(p.capital_expenditure)),
        ("End Cash", lambda p: _fmt_idr(p.end_cash_position)),
    ),
}


def display_ticker_financials(result: ViewTickerFinancialsResult) -> None:
    """Render one statement deep-dive."""
    display_ticker_financials_many((result,))


def display_ticker_financials_many(results: Sequence[ViewTickerFinancialsResult]) -> None:
    """Render one or more statement panels (default view shows all three)."""
    if not results:
        return

    console = Console()
    console.print("")
    multi = len(results) > 1
    ticker = results[0].ticker

    if multi:
        console.print(f"[bold]{ticker} · Financial statements[/bold]")
        console.print("")

    any_ok = False
    for result in results:
        if result.status == "ok":
            any_ok = True
        _render_one(console, result, compact_footer=multi)

    if multi:
        console.print(
            "[dim]Values in full currency units, abbreviated in display. "
            "Yahoo-mapped metric subsets — not full statement dumps. "
            "Income revenue definitions may differ across providers; "
            "NI incl. NCI is the strongest cross-check line.[/dim]"
        )
        console.print("")
        if not any_ok:
            hint = results[0].fetch_hint
            console.print(f"[dim]Hint: {hint}[/dim]")
            console.print("")
    elif results[0].status == "ok":
        _print_single_footer(console, results[0].statement)


def _render_one(
    console: Console,
    result: ViewTickerFinancialsResult,
    *,
    compact_footer: bool,
) -> None:
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
        if result.status == "empty" and result.fetch_hint and not compact_footer:
            console.print(f"[dim]Hint: {result.fetch_hint}[/dim]")
        console.print("")
        return

    summary = Text()
    summary.append(f"{result.statement.title()} statement (cached)  ", style="bold")
    latest = result.periods[0]
    summary.append(f"latest={latest.period_end.isoformat()}  ", style="cyan")
    if latest.currency:
        summary.append(f"currency={latest.currency}", style="dim")

    console.print(Panel(summary, title=title, subtitle=subtitle, border_style="cyan", expand=False))
    console.print("")
    console.print(_build_table(result.statement, result.periods))
    console.print("")


def _print_single_footer(console: Console, statement: FinancialStatementKind) -> None:
    if statement == "income":
        console.print(
            "[dim]Revenue definitions differ across providers; NI incl. NCI is the "
            "strongest cross-check line. Values in full currency units, abbreviated "
            "in display.[/dim]"
        )
    else:
        console.print(
            "[dim]Values in full currency units, abbreviated in display. "
            "Source metrics are yahoo-mapped subsets, not full statements.[/dim]"
        )
    console.print("")


def _build_table(
    kind: FinancialStatementKind,
    periods: tuple[CompanyFinancialPeriod, ...],
) -> Table:
    table = Table(show_header=True, header_style="bold magenta", expand=False)
    table.add_column("Period", style="cyan", no_wrap=True)
    columns = _COLUMNS[kind]
    for header, _ in columns:
        table.add_column(header, justify="right")
    table.add_column("Src", style="dim", no_wrap=True)

    for p in periods:
        cells = [p.period_end.isoformat()]
        cells.extend(fmt(p) for _, fmt in columns)
        cells.append(p.source)
        table.add_row(*cells)
    return table


def _fmt_eps(value: float | None) -> str:
    if value is None:
        return "\u2014"
    return f"{value:.2f}"
