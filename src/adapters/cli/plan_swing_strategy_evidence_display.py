"""
Strategy evidence panel for saham plan swing full output.

Layer: Adapter

Renders the historical backtest summary and the deterministic strategy
rule evidence (StrategyEvidence VO). DIAGNOSTIC-only: this panel must not
imply it controls TradeSetup.action.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import compact_table, console, panel


def print_strategy_evidence_panel(ctx: SwingOutputDisplayContext) -> None:
    ticker = ctx.ticker
    strategy_name = ctx.strategy_name
    backtest_result = ctx.evidence.backtest_result
    strategy_evidence = ctx.evidence.strategy_rule_evidence
    include_strategy = ctx.options.include_strategy

    history_group = []
    if include_strategy and backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        history_group.append(
            Text(
                f"Historical Backtest ({strategy_name}): {r.trade_count} trades", style="bold cyan"
            )
        )
        history_group.append(
            Text("Evidence only: this panel does not change TradeSetup.action.", style="dim")
        )
        period_start = getattr(r, "start_date", None)
        period_end = getattr(r, "end_date", None)
        period_text = (
            f"{period_start} to {period_end}"
            if period_start is not None and period_end is not None
            else "unknown"
        )
        hist_table = compact_table(show_header=False)
        hist_table.add_column("Metric", style="bold")
        hist_table.add_column("Value")

        win_style = (
            "green" if float(r.win_rate) >= 55 else ("yellow" if float(r.win_rate) >= 45 else "red")
        )
        avg_win_val = f"{float(r.avg_win):,.0f} IDR" if r.avg_win else "—"
        avg_loss_val = f"{float(r.avg_loss):,.0f} IDR" if r.avg_loss else "—"

        hist_table.add_row("Period", period_text)
        hist_table.add_row("Win Rate", f"[{win_style}]{float(r.win_rate):.1f}%[/]")
        hist_table.add_row("Profit Factor", f"{float(r.profit_factor):.2f}")
        hist_table.add_row("Max Drawdown", f"{float(r.max_drawdown_pct):.1f}%")
        hist_table.add_row("Avg Win/Loss", f"{avg_win_val} / {avg_loss_val}")
        history_group.append(hist_table)
    elif include_strategy and backtest_result is not None and backtest_result.trade_count == 0:
        history_group.append(Text(f"Historical Backtest ({strategy_name})", style="bold cyan"))
        if (
            getattr(backtest_result, "start_date", None) is not None
            and getattr(backtest_result, "end_date", None) is not None
        ):
            history_group.append(
                Text(
                    f"Period: {backtest_result.start_date} to {backtest_result.end_date}",
                    style="dim",
                )
            )
        history_group.append(
            Text("No trades triggered in available history (needs more broker data).", style="dim")
        )
        history_group.append(
            Text(
                f"Tip: run `saham backtest {ticker} --strategy {strategy_name} --verbose`",
                style="dim italic",
            )
        )
    elif include_strategy:
        history_group.append(Text("Historical Backtest", style="bold cyan"))
        history_group.append(
            Text(
                f"Could not run backtest. Run: `saham fetch market {ticker} --days 730`",
                style="dim yellow",
            )
        )

    # ── Strategy rule evidence (Phase D VO) ──────────────────────────────────
    if include_strategy and strategy_evidence is not None:
        history_group.append(Text(""))
        se = strategy_evidence
        _outcome_style = {
            "MATCHED": "bold green",
            "NOT_MATCHED": "yellow",
            "UNAVAILABLE": "dim",
            "INVALID": "bold red",
        }.get(se.outcome.value, "white")
        outcome_line = Text()
        outcome_line.append(f"Strategy Rule: {se.strategy_name}", style="bold cyan")
        outcome_line.append("  Outcome: ")
        outcome_line.append(se.outcome.value, style=_outcome_style)
        history_group.append(outcome_line)

        mr = se.matched_rule
        if mr is not None:
            rule_table = compact_table(show_header=False)
            rule_table.add_column("Field", style="bold")
            rule_table.add_column("Value")
            if mr.rule_name:
                rule_table.add_row("Rule", mr.rule_name)
            if mr.rule_outcome:
                rule_table.add_row("Rule outcome", mr.rule_outcome)
            if mr.setup_family:
                rule_table.add_row("Setup family", mr.setup_family)
            if mr.setup_phase:
                rule_table.add_row("Setup phase", mr.setup_phase)
            rule_table.add_row("Evidence route", mr.evidence_route)
            history_group.append(rule_table)
            for line in list(mr.rationale)[:3]:
                history_group.append(Text(f"  {line}", style="dim"))

        scores_table = compact_table(show_header=False)
        scores_table.add_column("Metric", style="bold")
        scores_table.add_column("Value")
        if se.coverage_score is not None:
            scores_table.add_row("Coverage", f"{se.coverage_score:.2f}")
        if se.conviction_score is not None:
            scores_table.add_row("Conviction", f"{se.conviction_score:.2f}")
        if se.freshness_score is not None:
            scores_table.add_row("Freshness", f"{se.freshness_score:.2f}")
        if (
            se.coverage_score is not None
            or se.conviction_score is not None
            or se.freshness_score is not None
        ):
            history_group.append(scores_table)

        if not mr:
            for line in list(se.rationale)[:3]:
                history_group.append(Text(f"  {line}", style="dim"))
        if se.unavailable_reasons:
            for reason in list(se.unavailable_reasons)[:2]:
                history_group.append(Text(f"  ⚠ {reason}", style="dim yellow"))

        history_group.append(
            Text(
                "  DIAGNOSTIC — strategy evidence does not control ENTER/WATCH/AVOID",
                style="dim",
            )
        )

    if history_group:
        console().print("")
        console().print(
            panel(
                Group(*history_group),
                title="STRATEGY EVIDENCE",
            )
        )
