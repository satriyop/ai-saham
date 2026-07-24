"""
Valuation, analyst consensus, earnings, and ownership panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _f, _fmt_idr, _not_cached, _pct
from src.domain.value_objects.earnings_record import EarningsRecord

EARNINGS_QUARTERS = 4
EARNINGS_PANEL_TITLE = "Earnings (last 4Q)"


def _valuation_panel(fund, fwd, latest_close: Decimal | None) -> object:
    tbl = compact_table(show_header=False)
    tbl.add_column("label", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value", no_wrap=True)
    tbl.add_column("label2", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value2", no_wrap=True)
    tbl.add_column("label3", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value3", no_wrap=True)

    close_str = f"Rp{latest_close:,.0f}" if latest_close else "\u2014"

    if fund is None:
        tbl.add_row("Close", close_str, "Fundamentals", "not cached", "", "")
    else:
        tbl.add_row(
            "Close",
            close_str,
            "52w High",
            f"Rp{_fmt_idr(fund.week52_high, suffix=False)}",
            "52w Low",
            f"Rp{_fmt_idr(fund.week52_low, suffix=False)}",
        )
        tbl.add_row(
            "PE (TTM)",
            _f(fund.pe_ratio_ttm),
            "PBV",
            _f(fund.pbv),
            "MCap",
            _fmt_idr(fund.market_cap_idr),
        )
        tbl.add_row(
            "ROE",
            _pct(fund.roe_ttm),
            "NPM",
            _pct(fund.net_profit_margin),
            "F-Score",
            str(fund.piotroski_f_score) if fund.piotroski_f_score is not None else "\u2014",
        )
        tbl.add_row(
            "Rev YoY",
            _pct(fund.revenue_yoy_growth),
            "Div Yield",
            _pct(fund.dividend_yield),
            "Fetched",
            str(fund.fetched_at.date()) if fund.fetched_at else "\u2014",
        )

    if fwd is not None:
        tbl.add_row(
            "Fwd PE",
            _f(fwd.forward_pe),
            "Fwd EPS",
            _fmt_idr(fwd.forward_eps_1y, suffix=False),
            "Rev Est",
            _fmt_idr(fwd.revenue_forward_1y),
        )

    return panel(tbl, title="Price & Valuation")


def _analyst_panel(ac) -> object:
    if ac is None:
        return panel(_not_cached(), title="Analyst Consensus")

    lines: list[Text] = []

    consensus_color = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}.get(
        ac.consensus_label, "white"
    )
    counts = f"{ac.buy_count}B \u00b7 {ac.hold_count}H \u00b7 {ac.sell_count}S"
    lines.append(
        Text(f"  {counts}  \u2192  ", style="default")
        + Text(ac.consensus_label, style=f"bold {consensus_color}")
    )

    if ac.avg_price_target:
        upside = f"  ({ac.upside_pct:+.1f}%)" if ac.upside_pct is not None else ""
        lines.append(Text(f"  Target  Rp{ac.avg_price_target:,.0f} avg{upside}", style="default"))

    if ac.price_target_low and ac.price_target_high:
        range_str = f"  Range   Rp{ac.price_target_low:,.0f} \u2013 Rp{ac.price_target_high:,.0f}"
        if ac.target_range_pct is not None:
            range_str += f"  (\u00b1{ac.target_range_pct:.0f}% spread)"
        lines.append(Text(range_str, style="default"))

    meta: list[str] = []
    if ac.last_updated:
        meta.append(f"Updated {ac.last_updated}")
    if ac.fetched_at:
        meta.append(f"Fetched {ac.fetched_at.date()}")
    if meta:
        lines.append(Text("  " + "  \u00b7  ".join(meta), style="dim"))

    return panel(Group(*lines), title="Analyst Consensus")


def _earnings_surprise_cell(record: EarningsRecord) -> Text:
    if record.eps_surprise_pct is None:
        return Text("\u2014", style="dim")
    label = "BEAT" if record.beat else "MISS"
    style = "green" if record.beat else "red"
    return Text(f"{label} {record.eps_surprise_pct:+.1f}%", style=style)


def _earnings_yoy_cell(record: EarningsRecord) -> Text:
    yoy = record.yoy_growth_pct
    if yoy is None:
        return Text("\u2014", style="dim")
    style = "green" if yoy > 0 else ("red" if yoy < 0 else "default")
    return Text(f"{yoy:+.1f}%", style=style)


def _earnings_panel(records: list[EarningsRecord]) -> object:
    """Show the most recent quarterly EPS history from cache."""
    if not records:
        return panel(_not_cached(), title=EARNINGS_PANEL_TITLE)

    tbl = compact_table()
    tbl.add_column("Period", style="dim", min_width=9)
    tbl.add_column("EPS", justify="right", min_width=7)
    tbl.add_column("YoY", justify="right", min_width=7)
    tbl.add_column("vs Est", justify="right", min_width=12)

    for record in records[:EARNINGS_QUARTERS]:
        eps = f"{record.eps_actual:.1f}" if record.eps_actual is not None else "\u2014"
        tbl.add_row(
            record.period_label,
            eps,
            _earnings_yoy_cell(record),
            _earnings_surprise_cell(record),
        )

    return panel(tbl, title=EARNINGS_PANEL_TITLE)


def _ownership_panel(sh) -> object:
    if sh is None:
        return panel(_not_cached(), title="Ownership")

    tbl = compact_table(show_header=False)
    tbl.add_column("label", style="dim", min_width=16)
    tbl.add_column("value")

    tbl.add_row(
        "Top Holder",
        f"{sh.top_holder_name}  {sh.top_holder_pct:.1f}%" if sh.top_holder_name else "\u2014",
    )
    tbl.add_row("Institutional", _pct(sh.institution_pct))
    tbl.add_row("Individual", _pct(sh.individual_pct))
    if sh.total_shares_formatted:
        tbl.add_row("Total Shares", sh.total_shares_formatted)
    if sh.report_date:
        tbl.add_row("Report Date", str(sh.report_date))
    if sh.fetched_at:
        tbl.add_row("Fetched", str(sh.fetched_at.date()))

    return panel(tbl, title="Ownership")
