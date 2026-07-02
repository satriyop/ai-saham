"""
Display helpers for saham trade backtest-swing command.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def display_swing_backtest(
    response: SwingBacktestResponse,
    show_trades: int,
    show_attribution: bool = False,
    show_tuning_plan: bool = False,
    show_tuning_proposal: bool = False,
    show_tuning_diff: bool = False,
) -> None:
    # Summary panel
    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")

    summary_table.add_row("Setup", response.setup)
    summary_table.add_row("Period", f"{response.start_date} to {response.end_date}")
    summary_table.add_row(
        "Transaction Cost",
        f"{float(response.cost_bps):g} bps one-way (applied on entry & exit)",
    )
    summary_table.add_row(
        "Simulation Logic",
        (
            "Scans each replay date, opens eligible signals within portfolio "
            "limits, then exits by TP/SL/max-hold."
        ),
    )

    console().print("")
    console().print(
        panel(
            summary_table,
            title="WALK-FORWARD SWING BACKTEST",
        )
    )

    # Core performance metrics table
    metrics_table = compact_table()
    metrics_table.add_column("Performance Metric", style="bold yellow")
    metrics_table.add_column("Value", justify="right")

    metrics_table.add_row("Initial capital", f"{float(response.initial_capital):,.0f} IDR")
    metrics_table.add_row("Final equity", f"{float(response.final_equity):,.0f} IDR")

    ret_val = response.total_return_pct
    ret_color = "green" if (ret_val or 0) >= 0 else "red"
    metrics_table.add_row("Total return", f"[{ret_color}]{_fmt_pct(ret_val, True)}[/]")

    dd_val = response.max_drawdown_pct
    metrics_table.add_row("Max drawdown", f"[red]{_fmt_pct(dd_val, True)}[/]")
    metrics_table.add_row("Trades count", str(response.trade_count))

    win_val = response.win_rate_pct
    win_color = (
        "green"
        if (win_val or 0) >= 55.0
        else "yellow"
        if (win_val or 0) >= 45.0
        else "red"
    )
    metrics_table.add_row("Win rate", f"[{win_color}]{_fmt_pct(win_val)}[/]")
    metrics_table.add_row("Avg trade return", _fmt_pct(response.avg_trade_return_pct, True))

    profit_factor = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    metrics_table.add_row("Profit factor", profit_factor)
    metrics_table.add_row("Exposure days ratio", _fmt_pct(response.exposure_pct))

    # Skips row
    skips_info = (
        f"no_cash={response.skipped_no_cash} | "
        f"duplicate={response.skipped_duplicate} | "
        f"no_forward_data={response.skipped_no_forward_data} | "
        f"regime={response.skipped_by_regime}"
    )
    metrics_table.add_row("Skipped orders count", skips_info)

    console().print(metrics_table)

    # Regime Performance (Panel 2)
    if response.regime_stats:
        regime_table = compact_table()
        regime_table.add_column("Regime", style="bold cyan")
        regime_table.add_column("Trades", justify="right")
        regime_table.add_column("Avg Return", justify="right")
        regime_table.add_column("Win Rate", justify="right")
        regime_table.add_column("Total PnL (IDR)", justify="right")

        for stat in response.regime_stats:
            pnl_color = "green" if stat.total_pnl >= 0 else "red"
            regime_table.add_row(
                stat.regime,
                str(stat.count),
                f"[{pnl_color}]{_fmt_pct(stat.avg_return_pct, True)}[/]",
                _fmt_pct(stat.win_rate_pct),
                f"[{pnl_color}]{float(stat.total_pnl):+,.0f}[/]"
            )
        console().print("")
        console().print(
            panel(
                regime_table,
                title="PERFORMANCE BY ENTRY REGIME",
            )
        )

    # Recent Trades (Panel 3)
    if show_trades > 0 and response.trades:
        trades_table = compact_table()
        trades_table.add_column("Entry Date")
        trades_table.add_column("Exit Date")
        trades_table.add_column("Ticker", style="bold")
        trades_table.add_column("Lots", justify="right")
        trades_table.add_column("Return", justify="right")
        trades_table.add_column("PnL (IDR)", justify="right")
        trades_table.add_column("Days", justify="right")
        trades_table.add_column("Exit Reason")

        for trade in response.trades[-show_trades:]:
            pnl_color = "green" if trade.pnl >= 0 else "red"
            trades_table.add_row(
                f"{trade.entry_date:%Y-%m-%d}",
                f"{trade.exit_date:%Y-%m-%d}",
                trade.ticker,
                str(trade.lots),
                f"[{pnl_color}]{_fmt_pct(trade.net_return_pct, True)}[/]",
                f"[{pnl_color}]{float(trade.pnl):+,.0f}[/]",
                str(trade.holding_days),
                trade.exit_reason
            )
        console().print("")
        console().print(
            panel(
                trades_table,
                title=f"RECENT {len(response.trades[-show_trades:])} TRADES",
            )
        )

    if show_attribution:
        _display_attribution_summary(response)

    if show_tuning_plan:
        _display_tuning_plan(response)

    if show_tuning_proposal:
        _display_tuning_proposal(response)

    if show_tuning_diff:
        _display_tuning_config_diff(response)

    # Warnings & Footnotes (Panel 4)
    warnings_list = []
    if response.warnings:
        for warning in response.warnings:
            warnings_list.append(Text(f"• {warning}", style="yellow"))

    footer_elements = []
    if warnings_list:
        footer_elements.extend([Text("Warnings", style="bold yellow"), *warnings_list, Text("")])
    footer_elements.append(
        Text(
            "DISCLAIMER: Historical simulation only. Not trading advice.",
            style="dim italic",
        )
    )

    console().print("")
    console().print(
        panel(
            Group(*footer_elements),
            title="Reference Notes"
        )
    )
    console().print("")


def _display_tuning_plan(response: SwingBacktestResponse) -> None:
    tuning_plan = build_tuning_readiness_plan(response.attribution_summary)
    table = compact_table(show_header=False)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value")
    table.add_row("Status", _quality_status_text(tuning_plan.status))
    table.add_row(
        "Can Propose Changes",
        "[green]yes[/]" if tuning_plan.can_propose_changes else "[red]no[/]",
    )
    table.add_row(
        "Evidence Scopes",
        ", ".join(tuning_plan.allowed_evidence_scopes) or "N/A",
    )
    table.add_row(
        "Config Families",
        ", ".join(tuning_plan.allowed_config_families) or "N/A",
    )
    table.add_row("Target Count", str(tuning_plan.target_count))
    if tuning_plan.blocked_reasons:
        table.add_row("Blocked Reasons", " | ".join(tuning_plan.blocked_reasons))
    table.add_row("Intent", tuning_plan.intent)

    console().print("")
    console().print(
        panel(
            table,
            title="TUNING READINESS PLAN",
        )
    )


def _display_tuning_proposal(response: SwingBacktestResponse) -> None:
    draft = build_tuning_proposal_draft(response.attribution_summary)
    table = compact_table()
    table.add_column("Priority", justify="right")
    table.add_column("Strength")
    table.add_column("Dimension", style="bold cyan")
    table.add_column("Family")
    table.add_column("Evidence")
    table.add_column("Action")

    for candidate in draft.candidate_changes[:8]:
        table.add_row(
            str(candidate.priority),
            candidate.evidence_strength,
            candidate.dimension,
            candidate.config_family,
            " | ".join(candidate.evidence_buckets),
            candidate.proposed_action,
        )

    if not draft.candidate_changes:
        table.add_row(
            "0",
            "N/A",
            "N/A",
            "N/A",
            "No candidate changes",
            "blocked",
        )

    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")
    summary_table.add_row("Status", draft.status)
    summary_table.add_row("Readiness", _quality_status_text(draft.readiness_status))
    summary_table.add_row("Candidate Changes", str(len(draft.candidate_changes)))
    summary_table.add_row("Rejected Changes", str(len(draft.rejected_changes)))
    summary_table.add_row("YAML Diff", "no")
    summary_table.add_row("Human Review", "required")
    if draft.evidence_notes:
        summary_table.add_row("Notes", " | ".join(draft.evidence_notes[:3]))

    console().print("")
    console().print(
        panel(
            Group(summary_table, Text(""), table),
            title="TUNING PROPOSAL DRAFT",
            subtitle=draft.intent,
        )
    )


def _display_tuning_config_diff(response: SwingBacktestResponse) -> None:
    draft = build_tuning_config_diff_draft(response.attribution_summary)
    summary_table = compact_table(show_header=False)
    summary_table.add_column("Metric", style="bold cyan")
    summary_table.add_column("Value")
    summary_table.add_row("Status", draft.status)
    summary_table.add_row("Proposal", draft.proposal_status)
    summary_table.add_row("Diff Items", str(len(draft.diff_items)))
    summary_table.add_row("Rejected Items", str(len(draft.rejected_items)))
    if draft.diff_items:
        summary_table.add_row(
            "Item Statuses",
            ", ".join(sorted({item.status for item in draft.diff_items})),
        )
        summary_table.add_row(
            "Value Policies",
            ", ".join(
                sorted({item.value_selection_policy for item in draft.diff_items})
            ),
        )
    summary_table.add_row("Can Apply", "no")
    summary_table.add_row("Human Review", "required")
    if draft.notes:
        summary_table.add_row("Notes", " | ".join(draft.notes[:3]))

    item_table = compact_table()
    item_table.add_column("Target", style="bold cyan")
    item_table.add_column("Evidence")
    item_table.add_column("Current", justify="right")
    item_table.add_column("Proposed", justify="right")
    item_table.add_column("Policy", overflow="fold")
    item_table.add_column("Rationale")
    for item in draft.diff_items[:8]:
        item_table.add_row(
            _fmt_target_path(item),
            _fmt_evidence_dimensions(item),
            _fmt_config_value(item.current_value),
            _fmt_config_value(item.proposed_value),
            item.value_selection_policy,
            item.rationale,
        )
    if not draft.diff_items:
        item_table.add_row(
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "No resolved diff candidates",
        )

    rejection_table = compact_table()
    rejection_table.add_column("Target Path", style="bold cyan")
    rejection_table.add_column("Evidence")
    rejection_table.add_column("Policy")
    rejection_table.add_column("Reason")
    for rejection in draft.rejected_items[:8]:
        rejection_table.add_row(
            rejection.target_path,
            rejection.evidence_dimension,
            rejection.value_selection_policy,
            rejection.reason,
        )
    if not draft.rejected_items:
        rejection_table.add_row("N/A", "N/A", "N/A", "No rejected candidates")

    console().print("")
    console().print(
        panel(
            Group(
                summary_table,
                Text(""),
                Text("Resolved Candidates", style="bold"),
                item_table,
                Text(""),
                Text("Rejected Candidates", style="bold"),
                rejection_table,
            ),
            title="TUNING CONFIG DIFF DRAFT",
            subtitle=draft.intent,
        )
    )


def _display_attribution_summary(response: SwingBacktestResponse) -> None:
    stats = (
        tuple(response.attribution_summary.group_stats)
        + tuple(response.attribution_summary.candidate_group_stats)
    )
    if not stats:
        return

    preferred_dimensions = (
        "trade_setup_action",
        "risk_status",
        "risk_gate",
        "signal_strength",
        "signal_score_bucket",
        "setup_gate",
        "regime",
        "signal_factor_bucket",
        "candidate_setup_match",
        "candidate_risk_status",
        "candidate_trade_setup_action",
        "candidate_signal_score_bucket",
        "candidate_signal_factor_bucket",
    )
    rows = []
    for dimension in preferred_dimensions:
        dimension_rows = [stat for stat in stats if stat.dimension == dimension]
        rows.extend(sorted(
            dimension_rows,
            key=lambda stat: (
                _stat_count(stat),
                _stat_avg_return(stat) or 0.0,
            ),
            reverse=True,
        )[:5])

    if not rows:
        return

    quality = response.attribution_summary.sample_quality
    quality_table = compact_table(show_header=False)
    quality_table.add_column("Metric", style="bold cyan")
    quality_table.add_column("Value")
    quality_table.add_row("Status", _quality_status_text(quality.status))
    quality_table.add_row(
        "Completed Trades",
        f"{quality.completed_trade_count}/{quality.min_sample_size}",
    )
    quality_table.add_row(
        "Candidate Observations",
        f"{quality.candidate_observation_count}/{quality.min_sample_size}",
    )
    if quality.notes:
        quality_table.add_row("Notes", " | ".join(quality.notes))

    table = compact_table()
    table.add_column("Dimension", style="bold cyan")
    table.add_column("Bucket")
    table.add_column("Samples", justify="right")
    table.add_column("Win", justify="right")
    table.add_column("Avg", justify="right")
    table.add_column("PF", justify="right")

    for stat in rows:
        avg = _stat_avg_return(stat) or 0.0
        style = "green" if avg > 0 else "red" if avg < 0 else "yellow"
        raw_profit_factor = _stat_profit_factor(stat)
        profit_factor = (
            "INF" if raw_profit_factor == float("inf")
            else "N/A" if raw_profit_factor is None
            else f"{raw_profit_factor:.2f}"
        )
        table.add_row(
            stat.dimension,
            stat.bucket,
            str(_stat_count(stat)),
            _fmt_pct(stat.win_rate_pct),
            f"[{style}]{_fmt_pct(_stat_avg_return(stat), True)}[/]",
            profit_factor,
        )

    console().print("")
    console().print(
        panel(
            quality_table,
            title="TUNING READINESS",
        )
    )
    console().print("")
    console().print(
        panel(
            table,
            title="TUNING ATTRIBUTION SUMMARY",
            subtitle=response.attribution_summary.intent,
        )
    )


def _quality_status_text(status: str) -> str:
    color = {
        "INSUFFICIENT_SAMPLE": "red",
        "CANDIDATE_ONLY": "yellow",
        "TRADE_READY": "green",
        "MIXED_READY": "green",
    }.get(status, "white")
    return f"[{color}]{status}[/]"


def _stat_count(stat) -> int:
    return getattr(stat, "trade_count", getattr(stat, "observation_count", 0))


def _stat_avg_return(stat) -> float | None:
    return getattr(
        stat,
        "avg_return_pct",
        getattr(stat, "avg_forward_return_pct", None),
    )


def _stat_profit_factor(stat) -> float | None:
    return getattr(stat, "profit_factor", None)


def _fmt_config_value(value: object | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list, tuple)):
        return type(value).__name__
    return str(value)


def _fmt_target_path(item) -> str:
    parsed = getattr(item, "parsed_target_path", None)
    if parsed is None:
        return item.target_path
    file_name = parsed.file_path.rsplit("/", maxsplit=1)[-1]
    leaf = parsed.document_path.rsplit(".", maxsplit=1)[-1]
    return f"{file_name}:{leaf}"


def _fmt_evidence_dimensions(item) -> str:
    dimensions = getattr(item, "evidence_dimensions", ()) or (
        item.evidence_dimension,
    )
    return ",".join(dimensions)
