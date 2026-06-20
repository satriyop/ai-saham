"""
Display helpers for accumulation CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.domain.services.trading_calendar import trading_sessions_apart
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_screener_config_typed

_SC = _load_swing_screener_config_typed()
_TABLE_WIDTH = 93


def format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def fmt_score(s: float | None) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= _SC.enter_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= _SC.watch_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = _SC.coiled_spring_min_score
    hot = [w for w in windows if candidates_by_window.get(w) and candidates_by_window[w].score >= threshold]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if c and c.score >= threshold and c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile:
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"


def notation_label(snapshot) -> str:
    if snapshot is None:
        return "-"
    parts = []
    if getattr(snapshot, "codes", None):
        parts.append(",".join(snapshot.codes))
    if getattr(snapshot, "tradeable", None) is False:
        parts.append("NO-TRADE")
    status = getattr(snapshot, "status", None)
    if status and status != "STATUS_ACTIVE":
        parts.append(status.replace("STATUS_", ""))
    if getattr(snapshot, "suspend_info", None):
        parts.append("SUSP")
    if getattr(snapshot, "has_uma", None):
        parts.append("UMA")
    return "+".join(parts) if parts else "-"


def notation_detail(snapshot) -> str:
    if snapshot is None:
        return ""
    bits = []
    label = notation_label(snapshot)
    if label != "-":
        bits.append(label)
    if snapshot.listing_board:
        bits.append(snapshot.listing_board)
    if snapshot.haircut_percentage:
        bits.append(f"haircut={snapshot.haircut_percentage}")
    return " | ".join(bits)


_STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}


def display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    granular: bool,
    vwap_only: bool,
    squeeze_only: bool,
    show_breakdown: bool,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    """Render accumulation screener results as terminal table."""
    candidates = response.candidates
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]
    if squeeze_only:
        candidates = [c for c in candidates if c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile]

    candidates = candidates[:top_n]

    if not candidates:
        empty = compact_table(show_header=False)
        empty.add_column("Message")
        empty.add_row("No candidates found matching the criteria.")
        empty.add_row(
            f"Checked {response.total_tickers_checked} tickers; "
            f"skipped {response.tickers_skipped} with insufficient data."
        )
        empty.add_row(f"Next: saham fetch market --universe {universe_label}")
        console().print(
            panel(
                empty,
                title=f"Foreign Accumulation - {universe_label.upper()}",
                subtitle=f"{response.window_days} sessions / {response.screened_at}",
            )
        )
        return

    table = compact_table()
    table.add_column("#", justify="right")
    table.add_column("Ticker", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Streak", justify="right")
    table.add_column("Net Days", justify="right")
    table.add_column("Net Value", justify="right")
    table.add_column("Flow%", justify="right")
    table.add_column("F_VWAP%", justify="right")
    table.add_column("RSI", justify="right")
    table.add_column("BB%ile", justify="right")
    table.add_column("Trend")
    if strategy_signals is not None:
        table.add_column("Strat")

    detail_lines: list[Text] = []

    for i, c in enumerate(candidates, 1):
        net_days_str = f"{c.net_buy_days}/{c.total_days}"
        vwap_str = f"{c.vwap_discount_pct:+.1f}%" if c.vwap_discount_pct is not None else "   —  "
        rsi_str = f"{c.rsi:.1f}" if c.rsi is not None else "  —"
        streak_str = f"{c.consecutive_streak}s"
        flow_str = f"{c.avg_flow_ratio:+.1f}" if c.avg_flow_ratio is not None else "   —"
        if c.bb_width_pctile is not None:
            pct_int = int(c.bb_width_pctile * 100)
            bb_style = "green" if c.bb_width_pctile <= _SC.coiled_spring_bb_pctile else (
                "yellow" if c.bb_width_pctile <= 0.40 else ""
            )
            bb_cell = Text(f"{pct_int}%", style=bb_style)
        else:
            bb_cell = Text("—", style="bright_black")

        # Color score
        if c.score >= _SC.enter_min_score:
            score_style = "green"
        elif c.score >= _SC.watch_min_score:
            score_style = "yellow"
        else:
            score_style = ""

        row = [
            str(i),
            c.ticker,
            Text(f"{c.score:.1f}", style=score_style),
            streak_str,
            net_days_str,
            format_value(c.total_net_value),
            flow_str,
            vwap_str,
            rsi_str,
            bb_cell,
            c.trend,
        ]
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            strat_style = "green" if raw == "LOW_RISK" else ("red" if raw == "HIGH_RISK" else "bright_black")
            row.append(Text(sym, style=strat_style))
        table.add_row(*row)

        if show_breakdown and c.score_breakdown:
            bd = c.score_breakdown
            detail_lines.append(Text(
                f"    [cons={bd.get('cons', 0):.1f} streak={bd.get('streak', 0):.1f}"
                f" vwap={bd.get('vwap', 0):.1f} rsi={bd.get('rsi', 0):.1f}"
                f" flow={bd.get('flow', 0):.1f} bb={bd.get('bb', 0):.1f}"
                f" inst={bd.get('inst', 0):.1f}]"
            ))

        notation_text = notation_detail(c.ticker_notation)
        if notation_text:
            detail_lines.append(Text(f"    {c.ticker} NOTATION: {notation_text}", style="yellow" if c.ticker_notation and c.ticker_notation.has_warning else ""))

        if c.seasonal_edge is not None:
            se = c.seasonal_edge
            se_style = "green" if se.is_tailwind else ("red" if se.is_headwind else "")
            detail_lines.append(Text(f"    {c.ticker} SEASONAL {se.label} (score {se.score:+.2f})", style=se_style))

        if c.dividend_risk:
            detail_lines.append(Text(f"    {c.ticker} DIVIDEND RISK", style="yellow"))
        if c.rights_issue_risk:
            detail_lines.append(Text(f"    {c.ticker} RIGHTS ISSUE", style="yellow"))
        if c.insider_buying:
            for label in c.recent_insider_buys:
                detail_lines.append(Text(f"    {c.ticker} INSIDER BUY - {label}", style="cyan"))

        if c.analyst_consensus is not None:
            ac = c.analyst_consensus
            if ac.is_bullish and (ac.upside_pct or 0) >= 10:
                ac_style = "green"
            elif ac.sell_count > ac.buy_count:
                ac_style = "red"
            else:
                ac_style = ""
            detail_lines.append(Text(f"    {c.ticker} ANALYST: {ac.label}", style=ac_style))

        if c.shareholding is not None:
            sh = c.shareholding
            sh_style = "cyan" if sh.institution_pct >= 30.0 else ""
            detail_lines.append(Text(f"    {c.ticker} HOLDING: {sh.label}", style=sh_style))

        if c.bandar_detector is not None:
            bd = c.bandar_detector
            if bd.accumulation_score >= 4:
                bd_style = "green"
            elif bd.is_accumulating:
                bd_style = "yellow"
            elif bd.is_distributing:
                bd_style = "red"
            else:
                bd_style = ""
            detail_lines.append(Text(f"    {c.ticker} BANDAR: {bd.label}", style=bd_style))

        if c.fundamentals is not None:
            fund = c.fundamentals
            if fund.is_quality:
                fund_style = "green"
            elif fund.roe_ttm is not None and fund.roe_ttm >= 10.0:
                fund_style = "yellow"
            else:
                fund_style = "red"
            detail_lines.append(Text(f"    {c.ticker} FUNDAM: {fund.label}", style=fund_style))

        missing = [
            label for label, val in [
                ("seasonal",  c.seasonal_edge),
                ("analyst",   c.analyst_consensus),
                ("holding",   c.shareholding),
                ("bandar",    c.bandar_detector),
                ("fundam",    c.fundamentals),
            ]
            if val is None
        ]
        if missing:
            detail_lines.append(Text(
                f"    {c.ticker} MISSING: {('  '.join(missing))}",
                style="dim",
            ))

        if granular and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.bci_label == "CLUSTER":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "STABLE":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "RETAIL-LED":
                broker_line += "  [BCI:RETAIL-LED]"
            detail_lines.append(Text(broker_line))

        if c.latest_candle_date is not None and c.latest_broker_date is not None:
            if c.latest_broker_date < c.latest_candle_date:
                lag = trading_sessions_apart(c.latest_broker_date, c.latest_candle_date)
                if lag > 0:
                    detail_lines.append(Text(
                        f"    {c.ticker} DATA LAG: broker as of {c.latest_broker_date}"
                        f" (+{lag} session{'s' if lag > 1 else ''} behind candle {c.latest_candle_date})"
                        f" → saham fetch market {c.ticker} --broker-only",
                        style="yellow",
                    ))
            elif c.latest_candle_date < c.latest_broker_date:
                lag = trading_sessions_apart(c.latest_candle_date, c.latest_broker_date)
                if lag > 0:
                    detail_lines.append(Text(
                        f"    {c.ticker} DATA LAG: candle as of {c.latest_candle_date}"
                        f" (+{lag} session{'s' if lag > 1 else ''} behind broker {c.latest_broker_date})"
                        f" → saham fetch market {c.ticker} --candles-only",
                        style="yellow",
                    ))

    sections = [table]
    if detail_lines:
        sections.append(Text("\nDetails", style="bold cyan"))
        sections.extend(detail_lines)

    console().print(
        panel(
            Group(*sections),
            title=f"Foreign Accumulation - {universe_label.upper()}",
            subtitle=f"{response.window_days} sessions / {response.screened_at}",
        )
    )

    # Render metadata guide cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    meta_table.add_row(
        "Stats",
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )

    if response.provider == "stockbit":
        meta_table.add_row(
            "Provider",
            "stockbit  ·  foreign aggregate from IDX  ·  broker detail: inst desk proxy (10 codes, not all-foreign)"
        )
    else:
        meta_table.add_row(
            "Provider",
            f"{response.provider} (aggregate foreign flow)\n"
            "For per-broker detail: run `saham fetch stockbit login`, then fetch with `--provider stockbit`"
        )

    explain_lines = [
        "FLOW%: avg net foreign % of total daily turnover (positive = accumulating)",
        "F_VWAP%: positive = price < foreign avg buy cost basis (foreigners underwater)",
        "BB%ILE: BB Width pctile vs last 60d — green(≤20%) = squeeze (coiled spring)",
        "Score 0–120 | consistency 40 | streak 30 | VWAP 20 | RSI 10 | flow 10 | BB 10 | BCI 0/5/15"
    ]
    if strategy_signals is not None:
        explain_lines.append(f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)")

    meta_table.add_row("Definitions", "\n".join(explain_lines))
    meta_table.add_row(
        "Disclaimer",
        "Swing trade watchlist — cross-check with `saham screen pre-open` for intraday entry timing.\n"
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Metadata & Guide",
        )
    )


def display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: "date",
    broker_quality: dict[str, ScreenBrokerQuality] | None = None,
) -> None:
    """Render multi-window side-by-side table."""
    windows = sorted(results.keys())

    # Build per-ticker dict: ticker -> {window -> candidate}
    by_ticker: dict[str, dict[int, AccumulationCandidate]] = {}
    for w, resp in results.items():
        for c in resp.candidates:
            by_ticker.setdefault(c.ticker, {})[w] = c

    # Apply squeeze filter
    if squeeze_only:
        by_ticker = {
            tk: pw for tk, pw in by_ticker.items()
            if any(
                c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20
                for c in pw.values()
            )
        }

    def sort_key(item: tuple) -> float:
        pw = item[1]
        scores = [c.score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        try:
            w = int(sort_by.rstrip("ds"))
            c = pw.get(w)
            return c.score if c else 0.0
        except (ValueError, AttributeError):
            return sum(scores) / len(scores)

    rows = sorted(by_ticker.items(), key=sort_key, reverse=True)[:top_n]

    if not rows:
        empty = compact_table(show_header=False)
        empty.add_column("Message")
        empty.add_row("No candidates found matching the criteria.")
        empty.add_row(f"Next: saham fetch market --universe {universe_label}")
        console().print(
            panel(
                empty,
                title=f"Foreign Accumulation - {universe_label.upper()}",
                subtitle=f"multi-window / {screened_at}",
            )
        )
        return

    table = compact_table()
    table.add_column("#", justify="right")
    table.add_column("Ticker", style="bold")
    for w in windows:
        table.add_column(f"{w}s", justify="right")
    table.add_column("Pattern")
    table.add_column("Trend")
    table.add_column("BRK")

    for i, (tk, pw) in enumerate(rows, 1):
        score_cells = []
        for w in windows:
            candidate = pw.get(w)
            if candidate is None:
                score_cells.append(Text("—", style="bright_black"))
                continue
            style = "green" if candidate.score >= 70 else ("yellow" if candidate.score >= 40 else "")
            score_cells.append(Text(f"{candidate.score:.0f}", style=style))
        pattern = classify_pattern(windows, pw)
        trend = next((c.trend for w in sorted(windows) for c in [pw.get(w)] if c), "—")
        quality = (broker_quality or {}).get(tk)
        brk = quality.label if quality else "n/a"
        table.add_row(str(i), tk, *score_cells, pattern, trend, brk)

    console().print(
        panel(
            table,
            title=f"Foreign Accumulation - {universe_label.upper()}",
            subtitle=f"multi-window / {screened_at}",
        )
    )

    # Render metadata guide cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    sample_resp = next(iter(results.values()))
    meta_table.add_row(
        "Stats",
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )

    meta_table.add_row(
        "Score Range",
        "Score ≥70 green | ≥40 yellow | <40 white"
    )

    meta_table.add_row(
        "Patterns:",
        "sustained | building | fresh rotation | long-term only | coiled spring | weak"
    )

    meta_table.add_row(
        "Broker Quality (BRK)",
        "named top-broker quality; smart+/noise+ = buyer-led, smart-/noise- = seller-led, n/a = no detail"
    )

    meta_table.add_row(
        "Disclaimer",
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Metadata & Guide",
        )
    )



def print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""
    # Top introductory text
    intro = Text(
        "Detects stocks being quietly bought by foreign institutions over\n"
        "multiple days. When foreigners accumulate consistently AND are\n"
        "'underwater' (bought higher than today's price), IHSG stocks\n"
        "resolve upward 65–70% of the time within 10–20 trading days.\n"
        "This is a swing trade watchlist (5–20 day horizon).\n",
        style="italic"
    )

    # Aligned Guide Table
    guide_table = compact_table()
    guide_table.add_column("Signal / Metric", style="bold yellow", width=22)
    guide_table.add_column("Value / Bench", style="cyan", width=20)
    guide_table.add_column("Details & Mechanics")

    guide_table.add_row(
        "SCORE (0–120)",
        "≥ 70 (green)\n40-69 (yellow)\n< 40 (white)",
        "Composite signal strength. Combines net days, streak, VWAP, RSI, flow, BB width, and BCI into a single score.\n- Green: Strong signal, worth research.\n- Yellow: Moderate watch, wait for confirmation.\n- White: Weak, likely noise, skip."
    )
    guide_table.add_row(
        "STREAK",
        "1-2d\n3-4d\n5-7d\n8d+",
        "Consecutive trading days foreigners were net buyers.\n- 5-7d: Strong, likely intentional.\n- 8d+: Very strong, committed.\nScoring: exponential curve (τ=7d). 7d ≈ 63%, 14d ≈ 86%."
    )
    guide_table.add_row(
        "NET_DAYS",
        "100%\n70-99%\n50-69%\n< 50%",
        "Consistency Ratio (net buy days / total sessions in window).\n- 100%: Every day was positive buy.\n- 70-99%: Most days positive.\n- < 50%: More sells than buys (not accumulating)."
    )
    guide_table.add_row(
        "NET_VALUE",
        "+19.4B\n+10M",
        "Total net foreign flow (buys − sells) in IDR over the window.\nConfirms real capital size behind the streak.\nT = trillion | B = billion | M = million (IDR)."
    )
    guide_table.add_row(
        "FLOW%",
        "0-5%\n5-15%\n15-30%\n30%+",
        "Average net foreign % of total daily turnover.\nA mid-cap at 35% FLOW% is a stronger signal than a large-cap at 3%.\nScoring: up to 10 pts, saturates at 20% flow ratio."
    )
    guide_table.add_row(
        "F_VWAP%",
        "> +5% (green)\n+1% to +5%\n< 0%",
        "Foreigners' VWAP to today's close price percentage.\n- Positive: foreigners bought higher than today's price (underwater, motivated to defend position).\n- Negative: foreigners in profit.\nScoring: 10% underwater = 20 pts."
    )
    guide_table.add_row(
        "RSI (14-day)",
        "> 70\n55-70\n40-55\n25-40\n< 25",
        "Relative Strength Index (0–100).\n- 25-40: Ideal entry zone.\n- > 70: Overbought.\nScoring: peak at RSI=40 (10 pts), zero at RSI≤25 or ≥75."
    )
    guide_table.add_row(
        "BB%ILE",
        "≤ 20% (green)\n21-40% (yellow)\n> 40%",
        "Bollinger Band width percentile vs last 60 days.\n- ≤ 20%: Squeeze (coiled spring, volatility compressed, ready to break).\nScoring: bottom 20th pctile earns 5–10 pts."
    )
    guide_table.add_row(
        "TREND",
        "UP\nDOWN\nSIDE",
        "Price relative to SMA20 (UP = >2% above, DOWN = >2% below, SIDE = within ±2%).\nDOWN or SIDE is often ideal to enter before the breakout."
    )
    guide_table.add_row(
        "PATTERN",
        "sustained\nbuilding\nfresh rotation\ncoiled spring",
        "Multi-window 7d/30d/90d evaluation.\n- sustained: score ≥60 on all windows.\n- building: strong 7d+30d, weak 90d.\n- coiled spring: BB squeeze + score ≥60 on any window."
    )
    guide_table.add_row(
        "BREAKDOWN",
        "cons / streak / vwap\nrsi / flow / bb / inst",
        "Score components: cons (40 pts), streak (30 pts), vwap (20 pts), rsi (10 pts), flow (10 pts), bb (10 pts), inst (15 pts BCI)."
    )

    checklist_text = Text(
        "  1. PATTERN = sustained or coiled spring  (multi-window confirms)\n"
        "  2. STREAK ≥ 5d                          (systematic, not opportunistic)\n"
        "  3. F_VWAP% > 0%                         (foreigners defending position)\n"
        "  4. BB%ILE ≤ 20% (green)                 (compressed, spring loaded)\n"
        "  5. RSI between 30–50                    (room to run)\n"
        "  6. FLOW% > 15%                          (foreigners dominating volume)\n"
        "  7. NET_DAYS ≥ 70%                       (consistent, not just a streak)",
        style="green"
    )

    tips_text = Text(
        "  • Run --multi first for the daily overview — one command, three windows.\n"
        "  • Use --squeeze-only to surface 'coiled spring' setups.\n"
        "  • Deep-dive: saham view broker flow <TICKER> --days 30\n"
        "               saham risk <TICKER> --profile balanced --with-sentiment",
        style="cyan"
    )

    console().print(
        panel(
            Group(
                intro,
                Text("Signals & Metrics Breakdown", style="bold cyan"),
                guide_table,
                Text("\nIdeal Candidate Checklist (Priority Order)", style="bold cyan"),
                checklist_text,
                Text("\nQuick Tips", style="bold cyan"),
                tips_text,
                Text("\nDISCLAIMER: Analysis only. Not financial advice.", style="dim italic")
            ),
            title="FOREIGN ACCUMULATION SCREENER — COLUMN GUIDE",
        )
    )

