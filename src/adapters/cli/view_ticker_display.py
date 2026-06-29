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
            return f"{v / 1e12:.2f} T"
        if abs(v) >= 1e9:
            return f"{v / 1e9:.2f} B"
        if abs(v) >= 1e6:
            return f"{v / 1e6:.2f} M"
    return f"{v:,.0f}"


def _fmt_vol(volume: int | None) -> str:
    if volume is None:
        return "—"
    if volume >= 1_000_000:
        return f"{volume / 1_000_000:.1f} M"
    if volume >= 1_000:
        return f"{volume / 1_000:.1f} K"
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
    if notation.fetched_at:
        lines.append(Text(f"  Fetched: {notation.fetched_at.date()}", style="dim"))

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
            str(fund.piotroski_f_score) if fund.piotroski_f_score is not None else "—",
        )
        tbl.add_row(
            "Rev YoY",
            _pct(fund.revenue_yoy_growth),
            "Div Yield",
            _pct(fund.dividend_yield),
            "Fetched",
            str(fund.fetched_at.date()) if fund.fetched_at else "—",
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
    counts = f"{ac.buy_count}B · {ac.hold_count}H · {ac.sell_count}S"
    lines.append(
        Text(f"  {counts}  →  ", style="default")
        + Text(ac.consensus_label, style=f"bold {consensus_color}")
    )

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
    if ac.fetched_at:
        meta.append(f"Fetched {ac.fetched_at.date()}")
    if meta:
        lines.append(Text("  " + "  ·  ".join(meta), style="dim"))

    return panel(Group(*lines), title="Analyst Consensus")


def _ownership_panel(sh) -> object:
    if sh is None:
        return panel(_not_cached(), title="Ownership")

    tbl = compact_table(show_header=False)
    tbl.add_column("label", style="dim", min_width=16)
    tbl.add_column("value")

    tbl.add_row(
        "Top Holder",
        f"{sh.top_holder_name}  {sh.top_holder_pct:.1f}%" if sh.top_holder_name else "—",
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


def _bandar_panel(snap) -> object:
    if snap is None:
        return panel(_not_cached(), title="Broker / Bandar Signal")

    acc_color = "green" if snap.is_accumulating else ("red" if snap.is_distributing else "yellow")

    lines: list[Text] = []
    lines.append(
        Text("  Overall: ", style="dim")
        + Text(snap.broker_accdist, style=f"bold {acc_color}")
        + Text(
            f"   Score {snap.accumulation_score:+d}   Broad {snap.broad_score:+d}", style="default"
        )
    )
    lines.append(
        Text(
            f"  Today: {snap.today_accdist}   5d: {snap.five_day_accdist}   "
            f"Top1: {snap.top1_accdist} ({snap.top1_percent:.0f}%)",
            style="default",
        )
    )

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

    if prof.fetched_at:
        lines.append(Text(f"  Fetched: {prof.fetched_at.date()}", style="dim"))

    return panel(Group(*lines), title="Company Profile")


def _candles_panel(candles: list) -> object:
    if not candles:
        return panel(_not_cached(), title="Recent Candles")

    recent = sorted(candles, key=lambda c: c.date, reverse=True)[:5]

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Open", justify="right")
    tbl.add_column("High", justify="right")
    tbl.add_column("Low", justify="right")
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


# ── New panels ───────────────────────────────────────────────────────────────


def _corp_action_panel(events: list) -> object:
    if not events:
        return panel(_not_cached(), title="Corporate Actions")

    events_sorted = sorted(
        [e for e in events if e.event_type != "__NONE__"],
        key=lambda e: (e.ex_date or e.cum_date or e.announcement_date or date.min),
        reverse=True,
    )
    if not events_sorted:
        return panel(_not_cached(), title="Corporate Actions")

    tbl = compact_table()
    tbl.add_column("Type", style="dim", min_width=10)
    tbl.add_column("Ex-date", min_width=11)
    tbl.add_column("Cum", min_width=11, style="dim")
    tbl.add_column("Detail")
    tbl.add_column("Status", min_width=8)

    for e in events_sorted[:8]:
        status_style = "green" if e.status == "active" else "dim"
        tbl.add_row(
            e.event_type.replace("_", " ").title(),
            str(e.ex_date) if e.ex_date else "—",
            str(e.cum_date) if e.cum_date else "—",
            e.detail or "—",
            Text(e.status or "—", style=status_style),
        )

    return panel(tbl, title="Corporate Actions")


def _insider_panel(txns: list) -> object:
    if not txns:
        return panel(_not_cached(), title="Insider Activity")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Name", min_width=18)
    tbl.add_column("Role", style="dim", min_width=10)
    tbl.add_column("Action", min_width=5)
    tbl.add_column("Shares", justify="right")
    tbl.add_column("Price", justify="right", style="dim")

    for t in txns[:8]:
        action_style = "green" if t.is_buy else "red"
        role_short = {"DIREKTUR": "Dir", "KOMISARIS": "Kom"}.get(
            t.role, t.role[:3] if t.role else "—"
        )
        tbl.add_row(
            str(t.transaction_date),
            t.name,
            role_short,
            Text(t.action_type, style=f"bold {action_style}"),
            f"{t.shares:,}",
            f"Rp{t.price:,.0f}" if t.price > 0 else "—",
        )

    return panel(tbl, title="Insider Activity (90d)")


def _seasonality_panel(edge, month: int) -> object:
    _MONTH_NAMES = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }
    month_name = _MONTH_NAMES.get(month, str(month))

    if edge is None:
        return panel(_not_cached(), title=f"Seasonality — {month_name}")

    if edge.is_tailwind:
        edge_label, edge_style = "Tailwind", "green"
    elif edge.is_headwind:
        edge_label, edge_style = "Headwind", "red"
    else:
        edge_label, edge_style = "Neutral", "yellow"

    sign = "+" if edge.avg_monthly_return_pct >= 0 else ""
    lines: list[Text] = [
        Text("  ")
        + Text(edge_label, style=f"bold {edge_style}")
        + Text(
            f"   {sign}{edge.avg_monthly_return_pct:.1f}% avg   {edge.win_rate_pct:.0f}% win-rate",
            style="default",
        ),
        Text(f"  {edge.positive_years} up / {edge.total_years} years of history", style="dim"),
    ]
    return panel(Group(*lines), title=f"Seasonality — {month_name}")


def _iev_panel(iev_rows: list) -> object:
    if not iev_rows:
        return panel(_not_cached(), title="IEV / Pre-open")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("IEV", justify="right", min_width=10)
    tbl.add_column("Rank", justify="right", min_width=5)
    tbl.add_column("IEP", justify="right", min_width=8)
    tbl.add_column("NCP", min_width=4)

    for row in iev_rows[:5]:
        ncp = Text("✓", style="green") if row.is_ncp_locked else Text("—", style="dim")
        tbl.add_row(
            str(row.date),
            _fmt_vol(row.iev),
            f"#{row.rank}",
            f"Rp{row.iep:,}" if row.iep else "—",
            ncp,
        )

    return panel(tbl, title="IEV / Pre-open")


def _sentiment_panel(logs: list) -> object:
    if not logs:
        return panel(_not_cached(), title="News Sentiment")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Sentiment", min_width=10)
    tbl.add_column("Catalyst", style="dim")
    tbl.add_column("Score", justify="right", min_width=5, style="dim")

    _SENTIMENT_STYLE = {"POSITIVE": "green", "NEGATIVE": "red", "NEUTRAL": "yellow"}

    for log in logs[:8]:
        style = _SENTIMENT_STYLE.get(log.sentiment.value, "default")
        tbl.add_row(
            str(log.date),
            Text(log.sentiment.value.title(), style=style),
            log.catalyst.value.replace("_", " ").title() if log.catalyst else "—",
            f"{log.score:.2f}",
        )

    return panel(tbl, title="News Sentiment")


# ── Main entry point ─────────────────────────────────────────────────────────


def show_ticker_view(ticker: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Render a read-only dashboard of all cached data for ticker."""
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_company_profile import StockbitCompanyProfileProvider
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
    from src.infrastructure.persistence.sentiment_repository import SQLiteSentimentRepository
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
    from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

    db = Path(db_path)

    notation_prov = StockbitTickerNotationProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    fund_prov = StockbitFundamentalsProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    analyst_prov = StockbitAnalystConsensusProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    sh_prov = StockbitShareholdingProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    bandar_prov = StockbitBandarDetectorProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    fwd_prov = StockbitForwardEstimatesProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    profile_prov = StockbitCompanyProfileProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    corp_action_repo = StockbitCorporateActionRepository(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    insider_prov = StockbitInsiderActivityProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    seasonality_prov = StockbitSeasonalityProvider(broker_provider=None, db_path=db)  # type: ignore[arg-type]
    market_repo = SQLiteMarketRepository(db)
    iev_repo = SQLiteIEVRepository(db)
    sentiment_repo = SQLiteSentimentRepository(db)

    today = date.today()

    notation = notation_prov._read_cache(ticker)
    fund = fund_prov._read_cache(ticker)
    analyst = analyst_prov._read_cache(ticker)
    sh = sh_prov._read_cache(ticker)
    bandar = bandar_prov._read_cache(ticker, today) or bandar_prov._read_cache(
        ticker, today - timedelta(1)
    )
    fwd = fwd_prov._read_cache(ticker)
    profile = profile_prov._read_cache(ticker)
    candles = market_repo.get_candles(ticker, start_date=today - timedelta(14), end_date=today)
    corp_actions = corp_action_repo._read_cache(
        ticker, today - timedelta(180), today + timedelta(180)
    )
    insider_txns = insider_prov._read_cache(ticker, today - timedelta(90), today, "ALL")
    seasonality = seasonality_prov._read_cache(ticker, today.year, today.month)

    # IEV: retrieve using repository
    iev_rows: list = []
    try:
        iev_rows = iev_repo.get_ticker_history(ticker, limit=5)
    except Exception:
        pass

    # Sentiment: retrieve using repository
    sentiment_logs: list = []
    try:
        sentiment_logs = sentiment_repo.get_ticker_logs(ticker, limit=8)
    except Exception:
        pass

    latest_close: Decimal | None = candles[-1].close if candles else None

    c = console()
    c.print()
    c.print(_identity_panel(ticker, notation))
    c.print(_valuation_panel(fund, fwd, latest_close))
    c.print(_analyst_panel(analyst))
    c.print(_ownership_panel(sh))
    c.print(_bandar_panel(bandar))
    c.print(_corp_action_panel(corp_actions))
    c.print(_insider_panel(insider_txns))
    c.print(_seasonality_panel(seasonality, today.month))
    c.print(_iev_panel(iev_rows))
    c.print(_sentiment_panel(sentiment_logs))
    c.print(_profile_panel(profile))
    c.print(_candles_panel(candles))
    c.print(
        Text(f"  Run `saham fetch market {ticker}` to refresh stale or missing data.", style="dim")
    )
    c.print()
