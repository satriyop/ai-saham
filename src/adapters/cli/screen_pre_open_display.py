"""
Display helpers for pre-open intraday CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.market_regime_use_case import MarketRegimeResponse
from src.application.use_case.pre_open_screen_use_case import PreOpenScreenConfig
from src.application.use_case.pre_open_workflow_use_case import PreOpenDataFreshness
from src.domain.value_objects.screener_result import ScreenerCandidate


def display_data_freshness(freshness: PreOpenDataFreshness | None) -> None:
    if freshness is None:
        return

    candle = freshness.candle_end.isoformat() if freshness.candle_end else "N/A"
    broker = freshness.broker_end.isoformat() if freshness.broker_end else "N/A"
    typer.echo("")
    typer.echo(
        "DATA: "
        f"Analysis date {freshness.analysis_date.isoformat()}   "
        f"Candles through {candle}   "
        f"Broker flow through {broker}"
    )


def fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    sign = "+" if signed else ""
    return f"{value:{sign}.2f}%"


def format_market_regime(response: MarketRegimeResponse) -> str:
    return (
        f"REGIME: {response.label} score={response.score}/7   "
        f"{response.benchmark_ticker} 20d {fmt_pct(response.benchmark_return_20d_pct, True)}   "
        f"Breadth SMA20 {fmt_pct(response.breadth_above_sma20_pct)}   "
        f"Foreign breadth {fmt_pct(response.foreign_flow_breadth_pct)}"
    )


def market_regime_warning(response: MarketRegimeResponse) -> str | None:
    if response.label == "RISK_OFF":
        return "Market regime is RISK_OFF; avoid marginal long scalps or cut size."
    if response.label == "WEAK":
        return "Market regime is WEAK; require cleaner opening confirmation or reduce size."
    return None


def display_market_regime(response: MarketRegimeResponse | None) -> None:
    if response is None:
        return
    typer.echo(format_market_regime(response))


def display_raw_movers(raw_movers: list, top_n: int | None, iev_min: int) -> None:
    """Print a compact summary of all movers fetched from IEV API before screener filtering."""
    if not raw_movers:
        return
    total = len(raw_movers)
    shown = top_n if top_n else total
    cap = min(shown, total)

    tickers_with_iev = []
    for mover in raw_movers[:20]:
        iep_suffix = f" @{mover.iep:,}" if mover.iep is not None else ""
        tickers_with_iev.append(f"{mover.ticker} {mover.iev / 1000:.0f}K{iep_suffix}")

    movers_text = []
    for i in range(0, len(tickers_with_iev), 5):
        chunk = tickers_with_iev[i:i+5]
        movers_text.append(Text("  |  ".join(chunk)))

    if total > 20:
        movers_text.append(Text(f"... and {total - 20} more below threshold", style="dim"))

    console().print("")
    console().print(
        panel(
            Group(*movers_text),
            title=f"Fetched {total} movers from Stockbit (top {cap} screened)"
        )
    )


VERDICT_ORDER = {"PRIME": 0, "WATCH": 1, "NO_DATA": 2, "SKIP": 3}


def verdict(candidate: ScreenerCandidate) -> str:
    """Synthesise all signals into a single action verdict."""
    if candidate.entry_range_low is None:
        return "NO_DATA"
    if candidate.trend_signal in ("BEARISH", "GAP_OUT") or candidate.accum_tag == "DISTRIBUTING":
        return "SKIP"
    if candidate.trend_signal == "NEUTRAL":
        return "SKIP"
    backed = candidate.accum_tag == "BACKED"
    floor = candidate.fvwap_discount_pct is not None and candidate.fvwap_discount_pct > 0
    if backed and floor:
        return "PRIME"
    return "WATCH"


def signal_col(candidate: ScreenerCandidate) -> str:
    """Compact ACCUM tag + FVWAP into a single SIGNAL string."""
    parts: list[str] = []
    if candidate.accum_tag is not None:
        tag = candidate.accum_tag[:8]
        streak = f"×{candidate.accum_streak}d" if candidate.accum_streak else ""
        parts.append(f"{tag}{streak}")
    if candidate.fvwap_discount_pct is not None:
        note = " floor" if candidate.fvwap_discount_pct > 0 else (
            " sell" if candidate.fvwap_discount_pct < -3 else ""
        )
        parts.append(f"{candidate.fvwap_discount_pct:+.1f}%{note}")
    if candidate.prev_high:
        parts.append(f"PH:{candidate.prev_high:,.0f}")
    return "  ".join(parts) if parts else "-"


def print_browser_plan(config: PreOpenScreenConfig) -> None:
    top_label = f"top {config.top_n}" if config.top_n else "all rows"
    steps = [
        Text("Claude Code: execute these steps, then re-run this command\n"
             "with --movers-json and --order-books-json flags.\n", style="bold yellow"),
        Text("STEP 1 — Fetch IEV Movers from Stockbit", style="bold cyan"),
        Text("  URL: https://stockbit.com/#/screener\n"
             "  1. Go to Screener → Movers section, click \"Selengkapnya\"\n"
             "  2. Sort by IEV column, descending\n"
             f"  3. Collect {top_label} with IEV >= {config.iev_min:,}\n"
             "  4. Build JSON array: [{\"ticker\": \"BBCA\", \"iev\": 150000}, ...]\n"),
    ]
    if not config.fast_mode:
        steps.extend([
            Text("STEP 2 — Fetch Order Books (for each ticker from Step 1)", style="bold cyan"),
            Text("  URL: https://stockbit.com/#/stock/{TICKER}/orderbook\n"
                 "  1. For each ticker: open order book tab\n"
                 "  2. Find the BID row with the LARGEST volume (lots)\n"
                 "  3. Record price and volume\n"
                 "  4. Build JSON object: {\"BBCA\": {\"price\": 8900, \"volume\": 50000}, ...}\n"),
            Text("STEP 3 — Re-run with collected data", style="bold cyan"),
            Text("  saham screen pre-open \\\n"
                 "    --movers-json '<step1_json>' \\\n"
                 "    --order-books-json '<step2_json>'", style="cyan")
        ])
    else:
        steps.extend([
            Text("STEP 2 — Re-run with movers data (fast mode — no order book needed)", style="bold cyan"),
            Text("  saham screen pre-open --fast --movers-json '<step1_json>'", style="cyan")
        ])

    console().print("")
    console().print(
        panel(
            Group(*steps),
            title="BROWSER ACTION PLAN — Pre-Open Screener"
        )
    )
    console().print("")


STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}
STRAT_COLOR = {
    "LOW_RISK": typer.colors.GREEN,
    "HIGH_RISK": typer.colors.RED,
    "MODERATE": typer.colors.BRIGHT_BLACK,
}


def display_pre_open_summary_panel(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: PreOpenDataFreshness | None,
    market_regime: MarketRegimeResponse | None,
) -> None:
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (VERDICT_ORDER.get(verdict(c), 99), -c.iev),
    )
    watchlist = [c for c in sorted_candidates if verdict(c) in ("PRIME", "WATCH")]
    skipped = [c for c in sorted_candidates if verdict(c) not in ("PRIME", "WATCH")]

    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Date", screened_date.isoformat())
    summary.add_row("IEV threshold", f">= {iev_min:,}")
    summary.add_row("Movers evaluated", str(total_movers_seen))
    summary.add_row("Candidates", str(len(candidates)))
    summary.add_row("Watchlist", str(len(watchlist)))
    summary.add_row("Skipped", str(len(skipped)))
    if data_freshness is not None:
        candle = data_freshness.candle_end.isoformat() if data_freshness.candle_end else "N/A"
        broker = data_freshness.broker_end.isoformat() if data_freshness.broker_end else "N/A"
        summary.add_row("Candles through", candle)
        summary.add_row("Broker flow through", broker)
    if market_regime is not None:
        summary.add_row("Market regime", f"{market_regime.label} ({market_regime.score}/7)")

    sections = [Text("Session Summary", style="bold cyan"), summary]
    if watchlist:
        sections.append(Text("Watchlist", style="bold green"))
        sections.append(Text("  ".join(c.ticker for c in watchlist), style="bold green"))
    else:
        sections.append(Text("Next", style="bold yellow"))
        sections.append(Text("Run: saham fetch iev, or retry with --iev-min 50000", style="yellow"))

    all_warnings = list(warnings)
    if data_freshness is not None:
        all_warnings.extend(data_freshness.warnings)
    if market_regime is not None:
        all_warnings.extend(market_regime.warnings)
    if all_warnings:
        warning_table = compact_table(show_header=False)
        warning_table.add_column("Warning")
        for warning in all_warnings[:5]:
            warning_table.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warning_table])

    console().print(
        panel(
            Group(*sections),
            title="Pre-Open Screener",
            subtitle=screened_date.isoformat(),
        )
    )


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


def display_results(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: PreOpenDataFreshness | None = None,
    market_regime: MarketRegimeResponse | None = None,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    # 1. Summary Panel
    display_pre_open_summary_panel(
        candidates=candidates,
        screened_date=screened_date,
        iev_min=iev_min,
        total_movers_seen=total_movers_seen,
        warnings=warnings,
        data_freshness=data_freshness,
        market_regime=market_regime,
    )

    if not candidates:
        console().print("")
        console().print(
            panel(
                Text("No candidates passed the IEV filter.", style="yellow"),
                title="Screener Results"
            )
        )
        return

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (VERDICT_ORDER.get(verdict(c), 99), -c.iev),
    )

    show_spread = any(c.spread_pct is not None for c in sorted_candidates)
    show_notation = any(notation_label(c.ticker_notation) != "-" for c in sorted_candidates)

    # 2. Results Table
    results_table = compact_table()
    results_table.add_column("Verdict")
    results_table.add_column("Ticker", style="bold")
    results_table.add_column("IEV", justify="right")
    results_table.add_column("Gap%", justify="right")
    if show_spread:
        results_table.add_column("Spread%", justify="right")
    results_table.add_column("Entry Range", justify="right")
    results_table.add_column("Stop%", justify="right")
    results_table.add_column("RSI", justify="right")
    results_table.add_column("Signal")
    if show_notation:
        results_table.add_column("Note")
    if strategy_signals is not None:
        results_table.add_column("Strat", justify="right")

    for candidate in sorted_candidates:
        current_verdict = verdict(candidate)

        # Colorize verdict
        if current_verdict == "PRIME":
            verdict_text = "[green]★ PRIME[/]"
        elif current_verdict == "WATCH":
            verdict_text = "[yellow]◉ WATCH[/]"
        elif current_verdict == "NO_DATA":
            verdict_text = "[dim]? NO_DATA[/]"
        else:
            verdict_text = "[red]✗ SKIP[/]"

        # Format gap
        gap_val = float(candidate.gap_pct) if candidate.gap_pct is not None else 0.0
        gap_color = "green" if gap_val > 0 else "red" if gap_val < 0 else "white"
        gap_text = f"[{gap_color}]{candidate.gap_label}[/]"

        rng = candidate.entry_range_label
        stop_pct = candidate.risk_reward_label
        rsi_str = f"{float(candidate.rsi):.0f}" if candidate.rsi else "-"
        signal = signal_col(candidate)

        row_cells = [
            verdict_text,
            candidate.ticker,
            f"{candidate.iev:,}",
            gap_text,
        ]

        if show_spread:
            row_cells.append(candidate.spread_label)

        row_cells.extend([
            rng,
            stop_pct,
            rsi_str,
            signal,
        ])

        if show_notation:
            row_cells.append(notation_label(candidate.ticker_notation))

        if strategy_signals is not None:
            raw = strategy_signals.get(candidate.ticker, "?")
            sym = STRAT_SYMBOL.get(raw, raw)
            if raw == "LOW_RISK":
                strat_text = "[green]↑[/]"
            elif raw == "HIGH_RISK":
                strat_text = "[red]↓[/]"
            else:
                strat_text = "[dim]~[/]"
            row_cells.append(strat_text)

        results_table.add_row(*row_cells)

    console().print("")
    console().print(
        panel(
            results_table,
            title="PRE-OPEN SCREENER RESULTS"
        )
    )

    # 3. AI Research Summaries
    has_ai = any(c.ai_summary for c in sorted_candidates)
    if has_ai:
        ai_elements = []
        for candidate in sorted_candidates:
            if candidate.ai_summary:
                ai_elements.append(Text(f"\n[{candidate.ticker}]", style="bold cyan"))
                ai_elements.append(Text(candidate.ai_summary))

        console().print("")
        console().print(
            panel(
                Group(*ai_elements),
                title="AI RESEARCH SUMMARIES"
            )
        )

    # 4. Next Action Panel
    watchlist = [c for c in sorted_candidates if verdict(c) in ("PRIME", "WATCH")]
    skipped = [c for c in sorted_candidates if verdict(c) not in ("PRIME", "WATCH")]

    footer_elements = []
    if watchlist:
        watch_labels = []
        for candidate in watchlist:
            prefix = "★" if verdict(candidate) == "PRIME" else "◉"
            watch_labels.append(f"{prefix} {candidate.ticker}")
        skip_labels = "  ".join(c.ticker for c in skipped) or "—"

        footer_elements.append(Text("WATCHLIST", style="bold green"))
        footer_elements.append(Text("  " + "  ".join(watch_labels), style="green"))
        footer_elements.append(Text("\nSKIP", style="bold dim"))
        footer_elements.append(Text("  " + skip_labels, style="dim"))

        tickers_json = ",".join(f'"{c.ticker}":___' for c in watchlist)
        footer_elements.append(Text("\nAt 09:00, fill opening prices and run:", style="bold"))
        footer_elements.append(Text(f"   saham trade confirm \\\n     --opening-json '{{{tickers_json}}}'", style="cyan"))
    else:
        footer_elements.append(Text("No candidates meet criteria today.", style="yellow"))
        footer_elements.append(Text("Consider: --iev-min 50000 or run 'saham fetch iev'", style="dim"))

    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="NEXT ACTION & TRACKING WATCHLIST"
        )
    )

    # 5. Explanations & Disclaimers
    legends = [
        Text("VERDICT: ★ PRIME = all signals green | ◉ WATCH = bullish, needs confirm | ✗ SKIP = bearish/distributing | ? NO_DATA = run 'saham fetch market TICKER --days 365'", style="dim"),
        Text("SIGNAL: ACCUM tag × streak | FVWAP% (floor=asing underwater, sell=asing profit) | PH=Prev High", style="dim"),
        Text("STOP%: max loss from entry (ATR-based, capped -7%)", style="dim"),
    ]
    if strategy_signals is not None:
        legends.append(
            Text(f"STRAT ({strategy_name}): ↑ = LOW_RISK(entry) | ~ = MODERATE(hold) | ↓ = HIGH_RISK(exit)", style="dim")
        )
    legends.append(Text("\nDISCLAIMER: Analysis only. Not trading advice.", style="dim italic"))

    console().print("")
    console().print(
        panel(
            Group(*legends),
            title="Reference & Explanation"
        )
    )
    console().print("")
