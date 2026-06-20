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
from src.application.use_case.market_regime import MarketRegimeResponse
from src.application.use_case.pre_open_screen import PreOpenScreenConfig
from src.application.use_case.pre_open_workflow import PreOpenDataFreshness
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

    typer.echo("")
    typer.echo(f"Fetched {total} movers from Stockbit (top {cap} screened):")

    tickers_with_iev = []
    for mover in raw_movers[:20]:
        iep_suffix = f" @{mover.iep:,}" if mover.iep is not None else ""
        tickers_with_iev.append(f"{mover.ticker} {mover.iev / 1000:.0f}K{iep_suffix}")
    row1 = "  " + "  |  ".join(tickers_with_iev[:10])
    typer.echo(row1)
    if len(tickers_with_iev) > 10:
        row2 = "  " + "  |  ".join(tickers_with_iev[10:])
        typer.echo(row2)
    if total > 20:
        typer.echo(f"  ... and {total - 20} more below threshold")
    typer.echo("")


VERDICT_ORDER = {"PRIME": 0, "WATCH": 1, "NO_DATA": 2, "SKIP": 3}


def verdict(candidate: ScreenerCandidate) -> str:
    """Synthesise all signals into a single action verdict."""
    if candidate.entry_range_low is None:
        return "NO_DATA"
    if candidate.trend_signal == "BEARISH" or candidate.accum_tag == "DISTRIBUTING":
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
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("BROWSER ACTION PLAN — Pre-Open Screener")
    typer.echo("=" * 60)
    typer.echo("")
    typer.echo("Claude Code: execute these steps, then re-run this command")
    typer.echo("with --movers-json and --order-books-json flags.")
    typer.echo("")
    typer.echo("STEP 1 — Fetch IEV Movers from Stockbit")
    typer.echo("-" * 40)
    typer.echo("  URL: https://stockbit.com/#/screener")
    typer.echo('  1. Go to Screener → Movers section, click "Selengkapnya"')
    typer.echo("  2. Sort by IEV column, descending")
    top_label = f"top {config.top_n}" if config.top_n else "all rows"
    typer.echo(f"  3. Collect {top_label} with IEV >= {config.iev_min:,}")
    typer.echo("  4. Build JSON array:")
    typer.echo('     [{"ticker": "BBCA", "iev": 150000}, ...]')
    typer.echo("")
    if not config.fast_mode:
        typer.echo("STEP 2 — Fetch Order Books (for each ticker from Step 1)")
        typer.echo("-" * 40)
        typer.echo("  URL: https://stockbit.com/#/stock/{TICKER}/orderbook")
        typer.echo("  1. For each ticker: open order book tab")
        typer.echo("  2. Find the BID row with the LARGEST volume (lots)")
        typer.echo("  3. Record price and volume")
        typer.echo("  4. Build JSON object:")
        typer.echo('     {"BBCA": {"price": 8900, "volume": 50000}, ...}')
        typer.echo("")
        typer.echo("STEP 3 — Re-run with collected data")
        typer.echo("-" * 40)
        typer.echo("  saham screen pre-open \\")
        typer.echo("    --movers-json '<step1_json>' \\")
        typer.echo("    --order-books-json '<step2_json>'")
    else:
        typer.echo("STEP 2 — Re-run with movers data (fast mode — no order book needed)")
        typer.echo("-" * 40)
        typer.echo("  saham screen pre-open --fast --movers-json '<step1_json>'")
    typer.echo("")
    typer.echo("=" * 60)


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
    display_pre_open_summary_panel(
        candidates=candidates,
        screened_date=screened_date,
        iev_min=iev_min,
        total_movers_seen=total_movers_seen,
        warnings=warnings,
        data_freshness=data_freshness,
        market_regime=market_regime,
    )

    typer.echo("")
    typer.echo("=" * 90)
    typer.echo("PRE-OPEN SCREENER RESULTS")
    typer.echo("=" * 90)
    typer.echo(f"Date: {screened_date}   IEV filter: >= {iev_min:,}")
    typer.echo(f"Movers evaluated: {total_movers_seen}   Candidates: {len(candidates)}")
    display_data_freshness(data_freshness)
    display_market_regime(market_regime)
    typer.echo("")

    if not candidates:
        typer.echo("No candidates passed the IEV filter.")
        typer.echo("=" * 90)
        return

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (VERDICT_ORDER.get(verdict(c), 99), -c.iev),
    )

    show_spread = any(c.spread_pct is not None for c in sorted_candidates)
    strat_header = f"  {'STRAT':>5}" if strategy_signals else ""
    sprd_header = f"  {'SPRD%':>6}" if show_spread else ""
    show_notation = any(notation_label(c.ticker_notation) != "-" for c in sorted_candidates)
    note_header = f"  {'NOTE':<10}" if show_notation else ""
    sep_width = 90 + (8 if strategy_signals else 0) + (9 if show_spread else 0) + (12 if show_notation else 0)
    header = (
        f"{'VERDICT':<10} {'TICKER':<7} {'IEV':>7}  {'GAP%':>6}"
        f"{sprd_header}  "
        f"{'ENTRY-RANGE':>16}  {'STOP%':>6}  {'RSI':>4}  {'SIGNAL'}"
        f"{note_header}{strat_header}"
    )
    typer.echo(header)
    typer.echo("-" * sep_width)

    verdict_style = {
        "PRIME": (typer.colors.GREEN, True, "★ PRIME  "),
        "WATCH": (typer.colors.YELLOW, False, "◉ WATCH  "),
        "NO_DATA": (typer.colors.BRIGHT_BLACK, False, "? NO_DATA"),
        "SKIP": (typer.colors.RED, False, "✗ SKIP   "),
    }

    for candidate in sorted_candidates:
        current_verdict = verdict(candidate)
        color, bold, label = verdict_style.get(current_verdict, (typer.colors.WHITE, False, current_verdict))
        verdict_str = typer.style(label, fg=color, bold=bold)

        gap = candidate.gap_label
        sprd_col = f"  {candidate.spread_label:>6}" if show_spread else ""
        rng = candidate.entry_range_label
        stop_pct = candidate.risk_reward_label
        rsi_str = f"{float(candidate.rsi):.0f}" if candidate.rsi else "-"
        signal = signal_col(candidate)
        note_col = f"  {notation_label(candidate.ticker_notation):<10}" if show_notation else ""

        strat_col = ""
        if strategy_signals is not None:
            raw = strategy_signals.get(candidate.ticker, "?")
            sym = STRAT_SYMBOL.get(raw, raw)
            col = STRAT_COLOR.get(raw, typer.colors.WHITE)
            strat_col = "  " + typer.style(f"{sym:>5}", fg=col, bold=(raw == "LOW_RISK"))

        typer.echo(
            f"{verdict_str} {candidate.ticker:<7} {candidate.iev:>7,}  {gap:>6}"
            f"{sprd_col}  "
            f"{rng:>16}  {stop_pct:>6}  {rsi_str:>4}  {signal}{note_col}{strat_col}"
        )

    typer.echo("-" * sep_width)

    has_ai = any(c.ai_summary for c in sorted_candidates)
    if has_ai:
        typer.echo("")
        typer.echo("AI RESEARCH SUMMARIES")
        typer.echo("-" * 90)
        for candidate in sorted_candidates:
            if candidate.ai_summary:
                typer.echo(f"\n[{candidate.ticker}]")
                typer.echo(candidate.ai_summary)

    all_warnings = list(warnings)
    if data_freshness is not None:
        all_warnings.extend(data_freshness.warnings)
    if market_regime is not None:
        all_warnings.extend(market_regime.warnings)
        regime_warning = market_regime_warning(market_regime)
        if regime_warning:
            all_warnings.append(regime_warning)

    if all_warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in all_warnings:
            typer.echo(f"  ! {warning}")

    watchlist = [c for c in sorted_candidates if verdict(c) in ("PRIME", "WATCH")]
    skipped = [c for c in sorted_candidates if verdict(c) not in ("PRIME", "WATCH")]

    typer.echo("")
    typer.echo("━" * 60)
    if watchlist:
        watch_labels = []
        for candidate in watchlist:
            prefix = "★" if verdict(candidate) == "PRIME" else "◉"
            watch_labels.append(f"{prefix} {candidate.ticker}")
        skip_labels = "  ".join(c.ticker for c in skipped) or "—"
        typer.echo(
            " WATCHLIST  " + typer.style("  ".join(watch_labels), fg=typer.colors.GREEN, bold=True)
        )
        typer.echo(
            " SKIP       " + typer.style(skip_labels, fg=typer.colors.BRIGHT_BLACK)
        )
        tickers_json = ",".join(f'"{c.ticker}":___' for c in watchlist)
        typer.echo("")
        typer.echo(" At 09:00, fill opening prices and run:")
        typer.echo(
            typer.style(
                f"   saham trade confirm \\\n"
                f"     --opening-json '{{{tickers_json}}}'",
                fg=typer.colors.CYAN,
            )
        )
    else:
        typer.echo(" No candidates meet criteria today.")
        typer.echo(" Consider: --iev-min 50000 or run 'saham fetch iev'")
    typer.echo("━" * 60)

    typer.echo("")
    typer.echo(
        "VERDICT: ★ PRIME=all signals green  ◉ WATCH=bullish, needs confirm  "
        "✗ SKIP=bearish/distributing  ? NO_DATA=run 'saham fetch market TICKER --days 365'"
    )
    typer.echo(
        "SIGNAL: ACCUM tag × streak  |  FVWAP% (floor=asing underwater, sell=asing profit)  |  PH=Prev High"
    )
    typer.echo("STOP%: max loss from entry (ATR-based, capped -7%)")
    if strategy_signals is not None:
        typer.echo(
            f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )
    typer.echo("")
    typer.echo("DISCLAIMER: Analysis only. Not trading advice.")
    typer.echo("=" * 90)
