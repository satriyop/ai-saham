"""
Display helpers for pre-open intraday CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
    context_factor_value,
    context_warnings,
)
from src.application.use_case.pre_open_screen_use_case import PreOpenScreenConfig
from src.application.use_case.pre_open_workflow_use_case import PreOpenDataFreshness
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import ScreenerCandidate
from src.domain.value_objects.trade_setup import SetupAction

SOURCE_STATUS_LABEL: dict[PreOpenSourceStatus, str] = {
    PreOpenSourceStatus.LIVE_SUCCESS: "LIVE",
    PreOpenSourceStatus.SNAPSHOT_SUCCESS: "SNAPSHOT",
    PreOpenSourceStatus.EMPTY_CONFIRMED: "EMPTY (confirmed)",
    PreOpenSourceStatus.UNAVAILABLE: "UNAVAILABLE",
    PreOpenSourceStatus.OUTSIDE_WINDOW: "OUTSIDE WINDOW",
}

SOURCE_STATUS_STYLE: dict[PreOpenSourceStatus, str] = {
    PreOpenSourceStatus.LIVE_SUCCESS: "green",
    PreOpenSourceStatus.SNAPSHOT_SUCCESS: "cyan",
    PreOpenSourceStatus.EMPTY_CONFIRMED: "yellow",
    PreOpenSourceStatus.UNAVAILABLE: "red",
    PreOpenSourceStatus.OUTSIDE_WINDOW: "red",
}


def no_candidates_message(
    source_status: PreOpenSourceStatus,
    source_message: str | None,
    source_snapshot_ref: str | None,
) -> str:
    if source_status == PreOpenSourceStatus.UNAVAILABLE:
        return (
            "Data source unavailable or returned an invalid payload — "
            f"{source_message or 'no details available'}."
        )
    if source_status == PreOpenSourceStatus.OUTSIDE_WINDOW:
        return f"Outside the pre-open window — {source_message or 'no live fetch attempted.'}"
    if source_status == PreOpenSourceStatus.EMPTY_CONFIRMED:
        return "Provider returned a valid empty mover list — no movers met the IEV threshold."
    if source_status == PreOpenSourceStatus.SNAPSHOT_SUCCESS:
        suffix = f" ({source_snapshot_ref})" if source_snapshot_ref else ""
        return f"Snapshot used{suffix} — no candidates passed the IEV filter."
    return "No candidates passed the IEV filter."


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


def format_market_regime(response: MarketContext) -> str:
    label = REGIME_DISPLAY_LABEL.get(response.regime.value, response.regime.value)
    score = context_conviction_score(response)
    breadth = context_factor_value(response, "idx_breadth")
    breadth_str = fmt_pct(breadth) if breadth is not None else "N/A"
    return f"REGIME: {label} score={score}/7   Breadth SMA20 {breadth_str}"


def market_regime_warning(response: MarketContext) -> str | None:
    if response.regime.value == "RISK_OFF":
        return "Market regime is RISK_OFF; avoid marginal long scalps or cut size."
    if response.regime.value == "VOLATILE":
        return "Market regime is VOLATILE; require cleaner opening confirmation or reduce size."
    return None


def display_market_regime(response: MarketContext | None) -> None:
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


def _trade_setup_action(
    ticker: str,
    trade_setup_by_ticker: dict | None,
) -> SetupAction | None:
    """Resolve canonical SetupAction from workflow TradeSetup map."""
    if not trade_setup_by_ticker:
        return None
    setup = trade_setup_by_ticker.get(ticker)
    if setup is None:
        return None
    return SetupAction.from_value(getattr(setup, "action", None))


def _format_action_text(action: SetupAction | None) -> str:
    if action is None:
        return "[dim]—[/]"
    if action is SetupAction.ENTER:
        return "[green]ENTER[/]"
    if action is SetupAction.WATCH:
        return "[yellow]WATCH[/]"
    if action.is_blocked:
        return f"[red]{action.value}[/]"
    return f"[dim]{action.value}[/]"


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
        steps.extend(
            [
                Text(
                    "STEP 2 — Re-run with movers data "
                    "(fast mode — no order book needed)",
                    style="bold cyan",
                ),
                Text(
                    "  saham screen pre-open --fast "
                    "--movers-json '<step1_json>'",
                    style="cyan",
                ),
            ]
        )

    console().print("")
    console().print(
        panel(
            Group(*steps),
            title="BROWSER ACTION PLAN — Pre-Open Screener"
        )
    )
    console().print("")


def display_pre_open_summary_panel(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: PreOpenDataFreshness | None,
    market_regime: MarketContext | None,
    source_status: PreOpenSourceStatus = PreOpenSourceStatus.LIVE_SUCCESS,
    source_message: str | None = None,
    source_snapshot_ref: str | None = None,
    trade_setup_by_ticker: dict | None = None,
    capture_phase: str = "UNKNOWN",
    source_is_live: bool = False,
    ncp_authoritative: bool = False,
    collection_started_at: datetime | None = None,
    decision_at: datetime | None = None,
) -> None:
    def _sort_key(c: ScreenerCandidate):
        action = _trade_setup_action(c.ticker, trade_setup_by_ticker)
        rank = action.display_sort_rank if action is not None else 99
        return (rank, -c.iev)

    sorted_candidates = sorted(candidates, key=_sort_key)
    actionable = [
        c
        for c in sorted_candidates
        if (a := _trade_setup_action(c.ticker, trade_setup_by_ticker)) is not None
        and a.is_open_watchlist
    ]
    non_actionable = [c for c in sorted_candidates if c not in actionable]

    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Date", screened_date.isoformat())
    status_label = SOURCE_STATUS_LABEL.get(source_status, source_status.value)
    status_style = SOURCE_STATUS_STYLE.get(source_status, "white")
    status_display = status_label
    if source_status == PreOpenSourceStatus.SNAPSHOT_SUCCESS and source_snapshot_ref:
        status_display = f"{status_label} ({source_snapshot_ref})"
    summary.add_row("Source", f"[{status_style}]{status_display}[/]")
    phase_display = capture_phase
    if not ncp_authoritative:
        phase_display = f"{capture_phase} (discovery-only)"
    summary.add_row("Decision phase", phase_display)
    summary.add_row(
        "Authority source",
        "direct live provider" if source_is_live else "discovery input",
    )
    if collection_started_at is not None:
        summary.add_row("Collection started", collection_started_at.isoformat())
    if decision_at is not None:
        summary.add_row("Collection finished", decision_at.isoformat())
    summary.add_row("IEV threshold", f">= {iev_min:,}")
    summary.add_row("Movers evaluated", str(total_movers_seen))
    summary.add_row("Candidates", str(len(candidates)))
    summary.add_row("Actionable (ENTER/WATCH)", str(len(actionable)))
    summary.add_row("Non-actionable", str(len(non_actionable)))
    if data_freshness is not None:
        candle = data_freshness.candle_end.isoformat() if data_freshness.candle_end else "N/A"
        broker = data_freshness.broker_end.isoformat() if data_freshness.broker_end else "N/A"
        summary.add_row("Candles through", candle)
        summary.add_row("Broker flow through", broker)
    if market_regime is not None:
        label = REGIME_DISPLAY_LABEL.get(market_regime.regime.value, market_regime.regime.value)
        score = context_conviction_score(market_regime)
        summary.add_row("Market regime", f"{label} ({score}/7)")

    sections = [Text("Session Summary", style="bold cyan"), summary]
    if actionable:
        sections.append(Text("Actionable", style="bold green"))
        sections.append(Text("  ".join(c.ticker for c in actionable), style="bold green"))
    else:
        sections.append(Text("Next", style="bold yellow"))
        sections.append(
            Text(
                "No ENTER/WATCH TradeSetup. Run: saham fetch iev, or retry with --iev-min 50000",
                style="yellow",
            )
        )

    all_warnings = list(warnings)
    if source_status != PreOpenSourceStatus.LIVE_SUCCESS and source_message:
        all_warnings.insert(0, f"Source ({status_label}): {source_message}")
    if data_freshness is not None:
        all_warnings.extend(data_freshness.warnings)
    if market_regime is not None:
        all_warnings.extend(context_warnings(market_regime))
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
    market_regime: MarketContext | None = None,
    risk_by_ticker: dict | None = None,
    signal_by_ticker: dict | None = None,
    trade_setup_by_ticker: dict | None = None,
    source_status: PreOpenSourceStatus = PreOpenSourceStatus.LIVE_SUCCESS,
    source_message: str | None = None,
    source_snapshot_ref: str | None = None,
    capture_phase: str = "UNKNOWN",
    source_is_live: bool = False,
    ncp_authoritative: bool = False,
    collection_started_at: datetime | None = None,
    decision_at: datetime | None = None,
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
        source_status=source_status,
        source_message=source_message,
        source_snapshot_ref=source_snapshot_ref,
        trade_setup_by_ticker=trade_setup_by_ticker,
        capture_phase=capture_phase,
        source_is_live=source_is_live,
        ncp_authoritative=ncp_authoritative,
        collection_started_at=collection_started_at,
        decision_at=decision_at,
    )

    if not candidates:
        message = no_candidates_message(source_status, source_message, source_snapshot_ref)
        style = SOURCE_STATUS_STYLE.get(source_status, "yellow")
        console().print("")
        console().print(
            panel(
                Text(message, style=style),
                title="Screener Results"
            )
        )
        return

    def _sort_key(c: ScreenerCandidate):
        action = _trade_setup_action(c.ticker, trade_setup_by_ticker)
        rank = action.display_sort_rank if action is not None else 99
        return (rank, -c.iev)

    sorted_candidates = sorted(candidates, key=_sort_key)

    show_spread = any(c.spread_pct is not None for c in sorted_candidates)
    show_notation = any(notation_label(c.ticker_notation) != "-" for c in sorted_candidates)

    # 2. Results Table — TradeSetup.action + signal score only (ADR-026 / ADR-048)
    results_table = compact_table()
    results_table.add_column("Action")
    results_table.add_column("Sig", justify="right")
    results_table.add_column("Ticker", style="bold")
    results_table.add_column("IEV", justify="right")
    results_table.add_column("Gap%", justify="right")
    results_table.add_column("Gap Src")
    if show_spread:
        results_table.add_column("Spread%", justify="right")
    results_table.add_column("Entry Range", justify="right")
    results_table.add_column("Stop%", justify="right")
    results_table.add_column("RSI", justify="right")
    if show_notation:
        results_table.add_column("Note")
    if risk_by_ticker is not None:
        results_table.add_column("Risk", justify="right")

    for candidate in sorted_candidates:
        # Format gap
        gap_val = float(candidate.gap_pct) if candidate.gap_pct is not None else 0.0
        gap_color = "green" if gap_val > 0 else "red" if gap_val < 0 else "white"
        gap_text = f"[{gap_color}]{candidate.gap_label}[/]"

        rng = candidate.entry_range_label
        stop_pct = candidate.risk_reward_label
        rsi_str = f"{float(candidate.rsi):.0f}" if candidate.rsi else "-"

        action = _trade_setup_action(candidate.ticker, trade_setup_by_ticker)
        action_text = _format_action_text(action)
        sig_sum = signal_by_ticker.get(candidate.ticker) if signal_by_ticker else None
        sig_text = f"{sig_sum.score}" if sig_sum is not None else "[dim]—[/]"

        row_cells: list = [
            action_text,
            sig_text,
            candidate.ticker,
            f"{candidate.iev:,}",
            gap_text,
            candidate.gap_price_source or "-",
        ]

        if show_spread:
            row_cells.append(candidate.spread_label)

        row_cells.extend([
            rng,
            stop_pct,
            rsi_str,
        ])

        if show_notation:
            row_cells.append(notation_label(candidate.ticker_notation))

        if risk_by_ticker is not None:
            summary = risk_by_ticker.get(candidate.ticker)
            if summary is None:
                strat_text = "[dim]?[/]"
            else:
                level = getattr(summary, "risk_level_name", None) or "?"
                if level == "LOW_RISK":
                    strat_text = "[green]↑[/]"
                elif level == "HIGH_RISK":
                    strat_text = "[red]↓[/]"
                else:
                    strat_text = "[dim]~[/]"
            row_cells.append(strat_text)

        results_table.add_row(*row_cells)

    console().print("")
    console().print(
        panel(
            results_table,
            title="PRE-OPEN CANDIDATES (TradeSetup)",
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

    # 4. Next Action Panel — SetupAction.is_open_watchlist (ENTER/WATCH)
    watchlist = [
        c
        for c in sorted_candidates
        if (a := _trade_setup_action(c.ticker, trade_setup_by_ticker)) is not None
        and a.is_open_watchlist
    ]
    skipped = [c for c in sorted_candidates if c not in watchlist]

    footer_elements = []
    if watchlist:
        watch_labels = []
        for candidate in watchlist:
            action = _trade_setup_action(candidate.ticker, trade_setup_by_ticker)
            prefix = "★" if action is SetupAction.ENTER else "◉"
            watch_labels.append(f"{prefix} {candidate.ticker}")
        skip_labels = "  ".join(c.ticker for c in skipped) or "—"

        footer_elements.append(Text("OPEN WATCHLIST (ENTER/WATCH)", style="bold green"))
        footer_elements.append(Text("  " + "  ".join(watch_labels), style="green"))
        footer_elements.append(Text("\nNON-WATCHLIST", style="bold dim"))
        footer_elements.append(Text("  " + skip_labels, style="dim"))

        tickers_json = ",".join(f'"{c.ticker}":___' for c in watchlist)
        footer_elements.append(Text("\nAt 09:00, fill opening prices and run:", style="bold"))
        footer_elements.append(
            Text(
                f"   saham trade confirm \\\n"
                f"     --opening-json '{{{tickers_json}}}'",
                style="cyan",
            )
        )
    else:
        footer_elements.append(
            Text("No ENTER/WATCH TradeSetup candidates today.", style="yellow")
        )
        footer_elements.append(
            Text("Consider: --iev-min 50000 or run 'saham fetch iev'", style="dim")
        )

    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="NEXT ACTION & TRACKING LIST"
        )
    )

    # 5. Explanations & Disclaimers
    legends = [
        Text(
            "ACTION: TradeSetup (ADR-026) sole production action | "
            "Sig = auction_ncp cascade 0-100 + open_viability veto (ADR-048)",
            style="dim",
        ),
        Text("STOP%: max loss from entry (ATR-based, capped -7%)", style="dim"),
    ]
    if risk_by_ticker is not None:
        legends.append(
            Text(
                "RISK (default gates, non-blocking): LOW / MODERATE / HIGH | ? = unavailable",
                style="dim",
            )
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
