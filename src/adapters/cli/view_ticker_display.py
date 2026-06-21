"""
show_ticker_view — read-only ticker information dashboard.

Reads all available SQLite-cached data for one ticker and renders it
as a series of Rich panels. Does NOT trigger any network fetch — callers
should run `saham fetch market TICKER` to populate/refresh caches.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel

DEFAULT_DB_PATH = Path("data.db")


def _fmt_idr(value: float | int | None, *, suffix: bool = True) -> str:
    if value is None:
        return "—"
    v = float(value)
    if suffix:
        if abs(v) >= 1e12:
            return f"{v/1e12:.2f} T"
        if abs(v) >= 1e9:
            return f"{v/1e9:.2f} B"
        if abs(v) >= 1e6:
            return f"{v/1e6:.2f} M"
    return f"{v:,.0f}"


def _fmt_vol(volume: int | None) -> str:
    if volume is None:
        return "—"
    if volume >= 1_000_000:
        return f"{volume/1_000_000:.1f} M"
    if volume >= 1_000:
        return f"{volume/1_000:.1f} K"
    return str(volume)


def _pct(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}%"


def _f(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def _not_cached() -> Text:
    return Text("  not cached", style="dim")


# ── Panel builders ───────────────────────────────────────────────────────────

def _identity_panel(ticker: str, notation) -> object:
    if notation is None:
        return panel(_not_cached(), title=f"[bold]{ticker}[/bold]")

    parts: list[str] = []
    if notation.listing_board:
        parts.append(notation.listing_board)
    if notation.sector:
        parts.append(notation.sector)
    if notation.sub_sector and notation.sub_sector != notation.sector:
        parts.append(notation.sub_sector)

    status_text = "✓ Tradeable" if notation.tradeable else "✗ Not Tradeable"
    status_style = "green" if notation.tradeable else "red"

    lines: list[Text] = []
    if parts:
        lines.append(Text("  " + " · ".join(parts), style="dim"))
    lines.append(Text(f"  {status_text}", style=status_style))
    if notation.codes_label and notation.codes_label != "-":
        lines.append(Text(f"  Notations: {notation.codes_label}", style="yellow"))
    if notation.suspend_info:
        lines.append(Text(f"  Suspend: {notation.suspend_info}", style="red"))
    if notation.fetched_date:
        lines.append(Text(f"  Fetched: {notation.fetched_date}", style="dim"))

    title = f"[bold]{ticker}[/bold]"
    if notation.listing_board:
        title += f"  [dim]{notation.listing_board}[/dim]"
    return panel(Group(*lines), title=title)


def _valuation_panel(fund, fwd, latest_close: Decimal | None) -> object:
    tbl = compact_table(show_header=False)
    tbl.add_column("label", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value", no_wrap=True)
    tbl.add_column("label2", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value2", no_wrap=True)
    tbl.add_column("label3", style="dim", no_wrap=True, min_width=14)
    tbl.add_column("value3", no_wrap=True)

    close_str = f"Rp{latest_close:,.0f}" if latest_close else "—"

    if fund is None:
        tbl.add_row("Close", close_str, "Fundamentals", "not cached", "", "")
    else:
        tbl.add_row(
            "Close", close_str,
            "52w High", f"Rp{_fmt_idr(fund.week52_high, suffix=False)}",
            "52w Low",  f"Rp{_fmt_idr(fund.week52_low, suffix=False)}",
        )
        tbl.add_row(
            "PE (TTM)", _f(fund.pe_ratio_ttm),
            "PBV",      _f(fund.pbv),
            "MCap",     _fmt_idr(fund.market_cap_idr),
        )
        tbl.add_row(
            "ROE",      _pct(fund.roe_ttm),
            "NPM",      _pct(fund.net_profit_margin),
            "F-Score",  str(fund.piotroski_f_score) if fund.piotroski_f_score is not None else "—",
        )
        tbl.add_row(
            "Rev YoY",  _pct(fund.revenue_yoy_growth),
            "Div Yield", _pct(fund.dividend_yield),
            "Fetched",  str(fund.fetched_date) if fund.fetched_date else "—",
        )

    if fwd is not None:
        tbl.add_row(
            "Fwd PE",   _f(fwd.forward_pe),
            "Fwd EPS",  _fmt_idr(fwd.forward_eps_1y, suffix=False),
            "Rev Est",  _fmt_idr(fwd.revenue_forward_1y),
        )

    return panel(tbl, title="Price & Valuation")


def _analyst_panel(ac) -> object:
    if ac is None:
        return panel(_not_cached(), title="Analyst Consensus")

    lines: list[Text] = []

    consensus_color = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}.get(ac.consensus_label, "white")
    counts = f"{ac.buy_count}B · {ac.hold_count}H · {ac.sell_count}S"
    lines.append(Text(f"  {counts}  →  ", style="default") + Text(ac.consensus_label, style=f"bold {consensus_color}"))

    if ac.avg_price_target:
        upside = f"  ({ac.upside_pct:+.1f}%)" if ac.upside_pct is not None else ""
        lines.append(Text(f"  Target  Rp{ac.avg_price_target:,.0f} avg{upside}", style="default"))

    if ac.price_target_low and ac.price_target_high:
        range_str = f"  Range   Rp{ac.price_target_low:,.0f} – Rp{ac.price_target_high:,.0f}"
        if ac.target_range_pct is not None:
            range_str += f"  (±{ac.target_range_pct:.0f}% spread)"
        lines.append(Text(range_str, style="default"))

    meta: list[str] = []
    if ac.last_updated:
        meta.append(f"Updated {ac.last_updated}")
    if meta:
        lines.append(Text("  " + "  ·  ".join(meta), style="dim"))

    return panel(Group(*lines), title="Analyst Consensus")


def _ownership_panel(sh) -> object:
    if sh is None:
        return panel(_not_cached(), title="Ownership")

    tbl = compact_table(show_header=False)
    tbl.add_column("label", style="dim", min_width=16)
    tbl.add_column("value")

    tbl.add_row("Top Holder", f"{sh.top_holder_name}  {sh.top_holder_pct:.1f}%" if sh.top_holder_name else "—")
    tbl.add_row("Institutional", _pct(sh.institution_pct))
    tbl.add_row("Individual", _pct(sh.individual_pct))
    if sh.total_shares_formatted:
        tbl.add_row("Total Shares", sh.total_shares_formatted)
    if sh.report_date:
        tbl.add_row("Report Date", str(sh.report_date))

    return panel(tbl, title="Ownership")


def _bandar_panel(snap) -> object:
    if snap is None:
        return panel(_not_cached(), title="Broker / Bandar Signal")

    acc_color = "green" if snap.is_accumulating else ("red" if snap.is_distributing else "yellow")

    lines: list[Text] = []
    lines.append(
        Text("  Overall: ", style="dim") +
        Text(snap.broker_accdist, style=f"bold {acc_color}") +
        Text(f"   Score {snap.accumulation_score:+d}   Broad {snap.broad_score:+d}", style="default")
    )
    lines.append(Text(
        f"  Today: {snap.today_accdist}   5d: {snap.five_day_accdist}   "
        f"Top1: {snap.top1_accdist} ({snap.top1_percent:.0f}%)",
        style="default",
    ))

    extras: list[str] = []
    if snap.top3_accdist:
        extras.append(f"Top3: {snap.top3_accdist}")
    if snap.top5_accdist:
        extras.append(f"Top5: {snap.top5_accdist}")
    if snap.top10_accdist:
        extras.append(f"Top10: {snap.top10_accdist}")
    if extras:
        lines.append(Text("  " + "   ".join(extras), style="default"))

    lines.append(Text(f"  Session: {snap.session_date}", style="dim"))

    return panel(Group(*lines), title="Broker / Bandar Signal")


def _profile_panel(prof) -> object:
    if prof is None:
        return panel(_not_cached(), title="Company Profile")

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
            bg += "…"
        lines.append(Text("  ─────────────────────────────────────────", style="dim"))
        lines.append(Text(f"  {bg}", style="dim"))

    if prof.fetched_date:
        lines.append(Text(f"  Fetched: {prof.fetched_date}", style="dim"))

    return panel(Group(*lines), title="Company Profile")


def _candles_panel(candles: list) -> object:
    if not candles:
        return panel(_not_cached(), title="Recent Candles")

    recent = sorted(candles, key=lambda c: c.date, reverse=True)[:5]

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Open", justify="right")
    tbl.add_column("High", justify="right")
    tbl.add_column("Low",  justify="right")
    tbl.add_column("Close", justify="right", style="bold")
    tbl.add_column("Volume", justify="right", style="dim")

    for c in recent:
        tbl.add_row(
            str(c.date),
            f"{c.open:,.0f}",
            f"{c.high:,.0f}",
            f"{c.low:,.0f}",
            f"{c.close:,.0f}",
            _fmt_vol(c.volume),
        )

    return panel(tbl, title="Recent Candles")


# ── Main entry point ─────────────────────────────────────────────────────────

def show_ticker_view(ticker: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Render a read-only dashboard of all cached data for ticker."""
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_company_profile import StockbitCompanyProfileProvider
    from src.infrastructure.browser.stockbit_forward_estimates import StockbitForwardEstimatesProvider
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
    from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

    db = Path(db_path)

    notation_prov  = StockbitTickerNotationProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    fund_prov      = StockbitFundamentalsProvider(broker_provider=None, db_path=db)    # type: ignore[arg-type]
    analyst_prov   = StockbitAnalystConsensusProvider(broker_provider=None, db_path=db)# type: ignore[arg-type]
    sh_prov        = StockbitShareholdingProvider(broker_provider=None, db_path=db)    # type: ignore[arg-type]
    bandar_prov    = StockbitBandarDetectorProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    fwd_prov       = StockbitForwardEstimatesProvider(broker_provider=None, db_path=db)# type: ignore[arg-type]
    profile_prov   = StockbitCompanyProfileProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    market_repo    = SQLiteMarketRepository(db)

    notation   = notation_prov._read_cache(ticker)
    fund       = fund_prov._read_cache(ticker)
    analyst    = analyst_prov._read_cache(ticker)
    sh         = sh_prov._read_cache(ticker)
    # Bandar: try today first, then yesterday (handles weekends / post-close)
    today = date.today()
    bandar = bandar_prov._read_cache(ticker, today) or bandar_prov._read_cache(ticker, today - timedelta(1))
    fwd        = fwd_prov._read_cache(ticker)
    profile    = profile_prov._read_cache(ticker)
    candles    = market_repo.get_candles(ticker, start_date=today - timedelta(14), end_date=today)

    latest_close: Decimal | None = candles[-1].close if candles else None

    c = console()
    c.print()
    c.print(_identity_panel(ticker, notation))
    c.print(_valuation_panel(fund, fwd, latest_close))
    c.print(_analyst_panel(analyst))
    c.print(_ownership_panel(sh))
    c.print(_bandar_panel(bandar))
    c.print(_profile_panel(profile))
    c.print(_candles_panel(candles))
    c.print(Text(f"  Run `saham fetch market {ticker}` to refresh stale or missing data.", style="dim"))
    c.print()
