"""
Flow / broker detail panel for saham analyze swing full output.

Layer: Adapter

This module renders facts already computed by the accumulation candidate,
longer-term flow detail, and broker attribution builders. It must not
compute business action, and must not introduce or alter thresholds.
"""

from __future__ import annotations

from decimal import Decimal

from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_broker_display import fmt_money_short, fmt_money_short_signed
from src.adapters.cli.analyze_swing_formatters import (
    flow_direction_label,
    fmt_date,
    fmt_pct,
    foreign_flow_evidence_label,
)
from src.adapters.cli.analyze_swing_institutional_display import (
    has_bandar_distribution,
    has_current_flow_confirmation,
)
from src.adapters.cli.analyze_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.rich_display import compact_table, console, panel


def print_flow_detail_panel(ctx: SwingOutputDisplayContext) -> None:
    accum = ctx.evidence.accumulation_candidate
    flow_detail = ctx.diagnostics.flow_detail
    broker_detail = ctx.diagnostics.broker_detail
    include_flow_detail = ctx.options.include_flow_detail
    window = ctx.window
    config = ctx.config

    flow_group = []
    if include_flow_detail and accum:
        evidence_label = foreign_flow_evidence_label(accum, config)
        flow_label = flow_direction_label(accum)
        flow_group.append(Text(
            f"Composite Foreign Flow Score ({window} broker sessions): "
            f"{evidence_label.upper()} / {flow_label.upper()}",
            style="bold cyan",
        ))
        flow_group.append(Text(
            "Scope: broker-flow and attribution diagnostics. SignalEngine uses the composite foreign-flow score below, not pure foreign net flow.",
            style="dim",
        ))
        flow_group.append(Text(
            "Longer-term flow context below is diagnostic only and does not directly change Verdict.",
            style="dim",
        ))

        flow_table = compact_table()
        flow_table.add_column("Foreign Flow Score")
        flow_table.add_column("Streak")
        flow_table.add_column("Net Days")
        flow_table.add_column("Flow Ratio")
        flow_table.add_column("F_VWAP%")
        flow_table.add_column("VWAP%")
        flow_table.add_column("BB%ile")
        flow_table.add_column("Trend")

        flow_str = f"{accum.avg_flow_ratio:+.1f}%" if accum.avg_flow_ratio is not None else "—"
        fvwap_str = f"{accum.vwap_discount_pct:+.1f}%" if accum.vwap_discount_pct is not None else "—"
        vwap_pct_str = f"{accum.vwap_pct:+.1f}%" if accum.vwap_pct is not None else "—"
        bb_str = f"{int(accum.bb_width_pctile * 100)}%" if accum.bb_width_pctile is not None else "—"
        net_str = f"{accum.net_buy_days}/{accum.total_days}"

        flow_table.add_row(
            f"{accum.foreign_flow_score:.1f}",
            f"{accum.consecutive_streak}s",
            net_str,
            flow_str,
            fvwap_str,
            vwap_pct_str,
            bb_str,
            accum.trend
        )
        flow_group.append(flow_table)

        if accum.foreign_flow_score >= config.watch_min_score and not has_current_flow_confirmation(accum):
            flow_group.append(Text(
                "Note: composite score is in watch-zone, but current foreign flow is not confirming "
                "(check Flow Ratio, Streak, and Net Days).",
                style="dim yellow",
            ))

        bd_for_note = getattr(accum, "bandar_detector", None)
        if has_bandar_distribution(bd_for_note):
            flow_group.append(Text(
                "Note: Bandar detector shows distribution; RiskEngine can block execution even when "
                "the composite Signal remains MODERATE.",
                style="dim red",
            ))

        score_breakdown = getattr(accum, "foreign_flow_score_breakdown", None)
        breakdown = getattr(score_breakdown, "breakdown_dict", None) or {}
        if breakdown:
            component_labels = {
                "cons": "Net-day consistency",
                "streak": "Buy streak",
                "vwap": "Foreign VWAP discount",
                "rsi": "RSI headroom",
                "flow": "Flow ratio",
                "bb": "BB squeeze",
                "inst": "Broker attribution",
            }
            component_table = compact_table()
            component_table.add_column("Foreign Flow Component")
            component_table.add_column("Pts", justify="right")
            for key, value in breakdown.items():
                component_table.add_row(
                    component_labels.get(key, key),
                    f"{value:.1f}",
                )
            flow_group.append(component_table)

        # Corp action risks & flags
        corp_flags = []
        if accum.dividend_risk:
            corp_flags.append(Text("⚠ DIVIDEND RISK — ex-date within hold window", style="yellow"))
        if accum.rights_issue_risk:
            corp_flags.append(Text("⚠ RIGHTS ISSUE — dilution risk within hold window", style="yellow"))
        for rups_detail in accum.upcoming_rups:
            corp_flags.append(Text(f"★ RUPS upcoming — {rups_detail}", style="cyan"))
        if accum.seasonal_edge is not None:
            se = accum.seasonal_edge
            se_color = "green" if se.is_tailwind else ("red" if se.is_headwind else "white")
            corp_flags.append(Text(f"★ SEASONAL {se.label} (accum bonus {se.score:+.2f})", style=se_color))
        if accum.insider_buying:
            for label_in in accum.recent_insider_buys:
                corp_flags.append(Text(f"⭐ INSIDER BUY — {label_in}", style="cyan"))
        if accum.analyst_consensus is not None:
            ac = accum.analyst_consensus
            ac_color = "green" if ac.is_bullish and (ac.upside_pct or 0) >= 10 else ("red" if ac.sell_count > ac.buy_count else "white")
            corp_flags.append(Text(f"📊 ANALYST: {ac.label}", style=ac_color))
        if accum.shareholding is not None:
            sh = accum.shareholding
            sh_color = "cyan" if sh.institution_pct >= 30.0 else "white"
            corp_flags.append(Text(f"🏦 HOLDING: {sh.label}", style=sh_color))
        if accum.bandar_detector is not None:
            bd = accum.bandar_detector
            bd_color = "green" if bd.accumulation_score >= 4 else ("yellow" if bd.is_accumulating else ("red" if bd.is_distributing else "white"))
            corp_flags.append(Text(f"🔍 BANDAR: {bd.label}", style=bd_color))
        if accum.fundamentals is not None:
            fund = accum.fundamentals
            fund_color = "green" if fund.is_quality else ("yellow" if fund.roe_ttm is not None and fund.roe_ttm >= 10.0 else "red")
            corp_flags.append(Text(f"📈 FUNDAM: {fund.label}", style=fund_color))

        if corp_flags:
            flow_group.append(Text("\nAdditional Signals & Flags", style="bold cyan"))
            for flag in corp_flags:
                flow_group.append(flag)

    if include_flow_detail and flow_detail:
        if flow_group:
            flow_group.append(Text(""))
        flow_group.append(Text(
            f"Longer-Term Flow Context ({flow_detail.window_sessions} broker sessions, diagnostic only) through {fmt_date(flow_detail.through_date)}",
            style="bold cyan",
        ))
        if (
            accum is not None
            and flow_detail.total_net_flow < Decimal("0")
            and has_current_flow_confirmation(accum)
        ):
            flow_group.append(Text(
                "Interpretation: recent signal-window accumulation is occurring inside a negative longer-term flow backdrop.",
                style="dim yellow",
            ))
        elif (
            accum is not None
            and flow_detail.total_net_flow < Decimal("0")
            and accum.foreign_flow_score >= config.watch_min_score
            and not has_current_flow_confirmation(accum)
        ):
            flow_group.append(Text(
                "Interpretation: longer-term flow is negative and the current signal window lacks foreign-flow confirmation.",
                style="dim yellow",
            ))
        elif accum is not None and flow_detail.total_net_flow > Decimal("0") and accum.foreign_flow_score < config.watch_min_score:
            flow_group.append(Text(
                "Interpretation: longer-term net buying exists, but the current signal window is still weak.",
                style="dim yellow",
            ))

        detail_flow_table = compact_table()
        detail_flow_table.add_column("Range")
        detail_flow_table.add_column("Sessions")
        detail_flow_table.add_column("Net Flow Value")
        detail_flow_table.add_column("Buy/Sell Ratio")
        detail_flow_table.add_column("Streak")
        detail_flow_table.add_column("Avg FLOW%")
        detail_flow_table.add_column("Latest FLOW%")

        latest_flow = fmt_money_short(flow_detail.latest_net_flow) if flow_detail.latest_net_flow is not None else "N/A"
        detail_flow_table.add_row(
            f"{fmt_date(flow_detail.from_date)} → {fmt_date(flow_detail.through_date)}",
            f"{flow_detail.available_sessions}/{flow_detail.window_sessions}",
            f"{fmt_money_short(flow_detail.total_net_flow)} IDR",
            f"{flow_detail.buy_sessions}B / {flow_detail.sell_sessions}S",
            f"{flow_detail.consecutive_buy_sessions}s",
            fmt_pct(flow_detail.avg_flow_ratio_pct, True),
            f"{latest_flow} ({fmt_pct(flow_detail.latest_flow_ratio_pct, True)})"
        )
        flow_group.append(detail_flow_table)

    if include_flow_detail and broker_detail:
        if flow_group:
            flow_group.append(Text(""))
        flow_group.append(Text(f"Attribution ({broker_detail.detail_sessions}/{broker_detail.window_sessions} sessions) via {broker_detail.source}", style="bold cyan"))

        # Side-by-side Buyer/Seller tables
        attribution_table = compact_table()
        attribution_table.add_column("Top Buyers", style="green")
        attribution_table.add_column("Top Sellers", style="red")

        max_len = max(len(broker_detail.top_buyers), len(broker_detail.top_sellers))
        for j in range(max_len):
            buy_str = ""
            if j < len(broker_detail.top_buyers):
                b = broker_detail.top_buyers[j]
                buy_str = f"{b.broker_code}: {fmt_money_short(b.net_value)} ({b.active_sessions}s)"

            sell_str = ""
            if j < len(broker_detail.top_sellers):
                s = broker_detail.top_sellers[j]
                sell_str = f"{s.broker_code}: {fmt_money_short(abs(s.net_value))} ({s.active_sessions}s)"

            attribution_table.add_row(buy_str, sell_str)
        flow_group.append(attribution_table)

        smart_share = f"{broker_detail.smart_share_pct:.1f}%" if broker_detail.smart_share_pct is not None else "N/A"
        buyer_share = f"{broker_detail.top_buyer_share_pct:.1f}%" if broker_detail.top_buyer_share_pct is not None else "N/A"
        seller_share = f"{broker_detail.top_seller_share_pct:.1f}%" if broker_detail.top_seller_share_pct is not None else "N/A"

        metrics_table = compact_table(show_header=False)
        metrics_table.add_column("Metric", style="bold")
        metrics_table.add_column("Value")
        metrics_table.add_row("Smart Money Flow", f"{fmt_money_short_signed(broker_detail.smart_flow)} IDR")
        metrics_table.add_row("Noise Flow", f"{fmt_money_short_signed(broker_detail.noise_flow)} IDR")
        metrics_table.add_row("Weighted Net Flow", f"{fmt_money_short_signed(broker_detail.weighted_net_flow)} IDR")
        metrics_table.add_row("Smart Share %", smart_share)
        metrics_table.add_row("Concentration", f"Top Buyer: {buyer_share} | Top Seller: {seller_share}")
        metrics_table.add_row("Quality Profile", f"{broker_detail.quality} ({broker_detail.broker_weight_quality})")
        flow_group.append(metrics_table)

    if flow_group:
        console().print("")
        console().print(
            panel(
                Group(*flow_group),
                title="FLOW / BROKER DETAIL",
            )
        )
