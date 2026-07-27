"""
Attribution summary rendering for policy accum CLI display.

Renders TUNING READINESS + TUNING ATTRIBUTION SUMMARY panels.
Only reads response.attribution_summary - does not call any tuning builders.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.policy_accum_display_formatters import (
    _fmt_pct,
    _quality_status_text,
    _stat_avg_return,
    _stat_count,
    _stat_profit_factor,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse


def display_swing_attribution(response: SwingBacktestResponse) -> None:
    """Render tuning attribution summary from response.

    Only reads response.attribution_summary.
    Does not call build_tuning_readiness_plan, build_tuning_proposal_draft,
    or build_tuning_config_diff_draft.
    Preserves current behavior: if no attribution rows exist, prints nothing.
    """

    stats = tuple(response.attribution_summary.group_stats) + tuple(
        response.attribution_summary.candidate_group_stats
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
        rows.extend(
            sorted(
                dimension_rows,
                key=lambda stat: (
                    _stat_count(stat),
                    _stat_avg_return(stat) or 0.0,
                ),
                reverse=True,
            )[:5]
        )

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
            "INF"
            if raw_profit_factor == float("inf")
            else "N/A"
            if raw_profit_factor is None
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
