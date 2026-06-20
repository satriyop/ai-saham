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

    typer.echo(
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )
    if response.provider == "stockbit":
        typer.echo(
            "Provider: stockbit  ·  foreign aggregate from IDX"
            "  ·  broker detail: inst desk proxy (10 codes, not all-foreign)"
        )
    else:
        typer.echo(f"Provider: {response.provider} (aggregate foreign flow)")
        typer.echo(
            "  For per-broker detail: run `saham fetch stockbit login`,"
            " then fetch with `--provider stockbit`"
        )
    typer.echo("")
    typer.echo("FLOW%: avg net foreign % of total daily turnover (positive = accumulating)")
    typer.echo("F_VWAP%: positive = price < foreign avg buy cost basis (foreigners underwater)")
    typer.echo("BB%ILE: BB Width pctile vs last 60d — green(≤20%) = squeeze (coiled spring)")
    typer.echo("Score 0–120 | consistency 40 | streak 30 | VWAP 20 | RSI 10 | flow 10 | BB 10 | BCI 0/5/15")
    if strategy_signals is not None:
        typer.echo(
            f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )
    typer.echo("")
    typer.echo("Swing trade watchlist — cross-check with `saham screen pre-open` for intraday entry timing.")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)

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

    sample_resp = next(iter(results.values()))
    typer.echo(
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )
    typer.echo("Score ≥70 green | ≥40 yellow | <40 white")
    typer.echo("Patterns: sustained | building | fresh rotation | long-term only | coiled spring | weak")
    typer.echo("BRK: named top-broker quality; smart+/noise+ = buyer-led, smart-/noise- = seller-led, n/a = no detail")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)


def print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""

    def _h(text: str) -> None:
        typer.echo("")
        typer.echo(typer.style(f"  {text}", fg=typer.colors.CYAN, bold=True))
        typer.echo(typer.style("  " + "─" * (len(text) + 2), fg=typer.colors.BRIGHT_BLACK))

    def _row(label: str, value: str) -> None:
        typer.echo(f"    {typer.style(label, fg=typer.colors.YELLOW):<30} {value}")

    typer.echo("")
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo(typer.style("  FOREIGN ACCUMULATION SCREENER — COLUMN GUIDE", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")
    typer.echo("  Detects stocks being quietly bought by foreign institutions over")
    typer.echo("  multiple days. When foreigners accumulate consistently AND are")
    typer.echo("  'underwater' (bought higher than today's price), IHSG stocks")
    typer.echo("  resolve upward 65–70% of the time within 10–20 trading days.")
    typer.echo("  This is a swing trade watchlist (5–20 day horizon).")

    # ── SCORE ──
    _h("SCORE  (0–120)")
    typer.echo("  Composite signal strength. Combines all signals below into one number.")
    typer.echo("  Higher = more confident that accumulation is real and setup is clean.")
    _row("≥ 70 (green)", "Strong signal — worth researching")
    _row("40–69 (yellow)", "Moderate — watch, wait for confirmation")
    _row("< 40 (white)", "Weak — likely noise, skip")
    typer.echo("")
    typer.echo("  Use --breakdown to see exactly how each component contributed.")

    # ── STREAK ──
    _h("STREAK  — Consecutive Buy Days")
    typer.echo("  How many trading days IN A ROW foreigners ended up as net buyers,")
    typer.echo("  counting backwards from today. A streak means systematic intent.")
    _row("1–2d", "Inconclusive")
    _row("3–4d", "Noteworthy — watch this ticker")
    _row("5–7d", "Strong — likely intentional accumulation")
    _row("8d+", "Very strong — institution is committed")
    typer.echo("")
    typer.echo("  Scoring: exponential curve (τ=7d). 7d streak ≈ 63% of max,")
    typer.echo("  14d ≈ 86%. Longer streaks always score higher — no hard cap.")

    # ── NET_DAYS ──
    _h("NET_DAYS  — Consistency Ratio  (e.g. 5/7)")
    typer.echo("  Net buy days / total broker sessions in the window. 5/7 =")
    typer.echo("  foreigners bought on 5 of the last 7 broker sessions. This is")
    typer.echo("  the highest-weight signal (40 pts).")
    _row("100% (4/4, 7/7)", "Every day was a buy — strong conviction")
    _row("70–99%", "Most days positive — healthy trend")
    _row("50–69%", "Mixed — watch for deterioration")
    _row("< 50%", "More sell days than buy — not accumulation")
    typer.echo("")
    typer.echo("  A stock with 4/4 is stronger than 10/30 even if the streak looks similar.")

    # ── NET_VALUE ──
    _h("NET_VALUE  — Total Net Foreign Flow (IDR)")
    typer.echo("  Total (foreign buys − foreign sells) over the broker-session window in IDR.")
    typer.echo("  Confirms real money is behind the consistency signal.")
    _row("+19.4B", "Net bought Rp 19.4 billion — meaningful size")
    _row("+10M", "Net bought Rp 10 million — may be too small")
    typer.echo("")
    typer.echo("  T = trillion  |  B = billion  |  M = million  (IDR)")

    # ── FLOW% ──
    _h("FLOW%  — Foreign Dominance of Daily Volume")
    typer.echo("  Average % of total daily turnover that was net foreign buying.")
    typer.echo("  Unlike NET_VALUE (absolute IDR), this is relative — a mid-cap")
    typer.echo("  at 35% FLOW% is a stronger signal than a large-cap at 3%.")
    _row("0–5%", "Minor participation")
    _row("5–15%", "Meaningful foreign interest")
    _row("15–30%", "Foreigners are a major force in this stock")
    _row("30%+", "Foreigners dominating — very strong signal")
    typer.echo("")
    typer.echo("  Scoring: contributes up to 10 pts, saturates at 20% flow ratio.")

    # ── F_VWAP% ──
    _h("F_VWAP%  — Foreigners' Profit / Loss on Position")
    typer.echo("  Compares foreigners' average buy price (VWAP) to today's price.")
    typer.echo("")
    typer.echo("  POSITIVE (+8.4%) = foreigners bought HIGHER than today's price.")
    typer.echo("  They are underwater (in a paper loss) and motivated to defend.")
    typer.echo("  When they keep buying despite a loss, they expect a recovery.")
    typer.echo("  This creates a price floor — they absorb selling to protect position.")
    typer.echo("")
    typer.echo("  NEGATIVE (−1.9%) = foreigners are in profit. Less urgency to defend.")
    _row("  > +5%", "Meaningfully underwater — strong defense motive")
    _row("  +1% to +5%", "Slightly underwater — moderate signal")
    _row("  < 0%", "In profit — less motivated to defend")
    _row("  — (dash)", "Insufficient buy data to compute VWAP")
    typer.echo("")
    typer.echo("  Scoring: linear ramp. 10% underwater = full 20 pts. 5% = 10 pts.")

    # ── RSI ──
    _h("RSI  — Room Left to Run  (14-day)")
    typer.echo("  Relative Strength Index — measures price momentum (0–100).")
    typer.echo("  For accumulation, you want to enter BEFORE a move, not after.")
    _row("  > 70", "Overbought — most of the move already happened")
    _row("  55–70", "Building momentum — getting stretched")
    _row("  40–55", "Healthy — moving but not overextended")
    _row("  25–40", "Weak/recovering — ideal entry zone")
    _row("  < 25", "Severe panic — high risk, possible capitulation")
    typer.echo("")
    typer.echo("  Scoring: tent peak at RSI=40 (10 pts). Zero at RSI≤25 or ≥75.")
    typer.echo("  RSI 40 with a 5-day streak = smart money re-entering during weakness.")

    # ── BB%ILE ──
    _h("BB%ILE  — Bollinger Band Squeeze  (green ≤ 20%)")
    typer.echo("  Percentile rank of today's Bollinger Band width vs last 60 days.")
    typer.echo("  BB Width measures price channel size — narrow = compressed volatility.")
    typer.echo("")
    typer.echo("  LOW BB%ILE = the band is TIGHTER than usual = SQUEEZE.")
    typer.echo("  When a stock trades flat (low vol) while foreigners accumulate,")
    typer.echo("  it is a 'coiled spring'. Compression releases suddenly on a catalyst.")
    _row("  ≤ 20% (green)", "Squeeze — coiled spring, watch closely")
    _row("  21–40% (yellow)", "Moderately tight — building")
    _row("  > 40%", "Normal or expanding volatility")
    _row("  — (dash)", "< 60 days of price data in local DB")
    typer.echo("")
    typer.echo("  Scoring: bottom 20th pctile earns 5–10 pts; 40th pctile earns 0–5 pts.")
    typer.echo("  Use --squeeze-only to filter exclusively for these setups.")

    # ── TREND ──
    _h("TREND  — Price vs SMA20")
    typer.echo("  Whether the stock is above or below its 20-day moving average.")
    _row("  UP", "> 2% above SMA20 — uptrend")
    _row("  DOWN", "> 2% below SMA20 — downtrend")
    _row("  SIDE", "Within ±2% of SMA20 — ranging")
    typer.echo("")
    typer.echo("  For accumulation setups, DOWN or SIDE is often ideal — you want to")
    typer.echo("  enter BEFORE the trend turns UP, not after the move has started.")

    # ── PATTERN (multi-window) ──
    _h("PATTERN  — Multi-Window Summary  (--multi only)")
    typer.echo("  Labels what the 7d/30d/90d score comparison reveals.")
    _row("  sustained", "Score ≥60 on all 3 windows — months of buildup, highest conviction")
    _row("  building", "Strong 7d+30d, weaker 90d — accumulation intensifying recently")
    _row("  fresh rotation", "Strong 7d only — very recent, needs time to confirm")
    _row("  long-term only", "Strong 90d, weak recent — may be complete, watch for exit")
    _row("  coiled spring", "Squeeze + score ≥60 on any window — compressed, ready to break")
    _row("  weak", "No window scores ≥60 — not a meaningful setup")

    # ── BREAKDOWN ──
    _h("SCORE BREAKDOWN  (--breakdown flag)")
    typer.echo("  Shows exactly how each component contributed to the total score.")
    typer.echo("  Format: [cons=X streak=X vwap=X rsi=X flow=X bb=X inst=X]")
    _row("  cons", "Up to 40 pts — net buy day consistency")
    _row("  streak", "Up to 30 pts — consecutive buy days (exponential)")
    _row("  vwap", "Up to 20 pts — how underwater foreigners are")
    _row("  rsi", "Up to 10 pts — RSI headroom (tent at 40)")
    _row("  flow", "Up to 10 pts — avg % of daily turnover that's foreign")
    _row("  bb", "Up to 10 pts — BB Width squeeze intensity")
    _row("  inst", "0/5/15 pts — BCI: RETAIL-LED/STABLE/CLUSTER (Stockbit only)")
    typer.echo("")
    typer.echo("  If a stock scores lower than expected, breakdown shows which signal")
    typer.echo("  is missing. E.g. vwap=0 means foreigners are in profit — no defense motive.")

    # ── IDEAL SETUP ──
    _h("IDEAL CANDIDATE CHECKLIST")
    typer.echo("  In priority order:")
    typer.echo("    1. PATTERN = sustained or coiled spring  (multi-window confirms)")
    typer.echo("    2. STREAK ≥ 5d                          (systematic, not opportunistic)")
    typer.echo("    3. F_VWAP% > 0%                         (foreigners defending position)")
    typer.echo("    4. BB%ILE ≤ 20% (green)                 (compressed, spring loaded)")
    typer.echo("    5. RSI between 30–50                    (room to run)")
    typer.echo("    6. FLOW% > 15%                          (foreigners dominating volume)")
    typer.echo("    7. NET_DAYS ≥ 70%                       (consistent, not just a streak)")
    typer.echo("")
    typer.echo("  No single signal is definitive. A stock meeting 5 of 7 criteria is")
    typer.echo("  a much stronger candidate than one barely crossing a score threshold.")

    # ── TIPS ──
    _h("QUICK TIPS")
    typer.echo("  Run --multi first for the daily overview — one command, three windows.")
    typer.echo("  Use --squeeze-only to surface 'coiled spring' setups.")
    typer.echo("  Deep-dive: saham view broker flow <TICKER> --days 30")
    typer.echo("             saham risk <TICKER> --profile balanced --with-sentiment")
    typer.echo("")
    typer.echo(typer.style("  DISCLAIMER: Analysis only. Not financial advice.", fg=typer.colors.BRIGHT_BLACK))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")
