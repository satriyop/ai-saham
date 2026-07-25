"""
Column guide display for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.shared.score_display_labels import (
    ACCUM,
    ACCUM_DEFINITION,
    FLOW_GRP,
    FLOW_RATIO_PCT,
    SETUP_GRP,
    SIGNAL,
    SIGNAL_DEFINITION,
)


def print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""
    # Top introductory text
    intro = Text(
        "Detects stocks being quietly bought by foreign institutions over\n"
        "multiple days. Performance evidence: not yet independently\n"
        "validated. Treat this screen as deterministic evidence ranking,\n"
        "not a calibrated prediction. Use the learning/grade workflow\n"
        "after enough observations are collected to measure local\n"
        "resolution rates. This is a swing trade watchlist (5–20 day\n"
        "horizon).\n\n"
        f"Vocabulary (ADR-043): {ACCUM} ≠ {SIGNAL}. "
        f"{FLOW_RATIO_PCT} is an Accum component; {FLOW_GRP} is a Signal group.\n",
        style="italic"
    )

    # Aligned Guide Table
    guide_table = compact_table()
    guide_table.add_column("Metric", style="bold yellow", width=22)
    guide_table.add_column("Value / Bench", style="cyan", width=20)
    guide_table.add_column("Details & Mechanics")

    guide_table.add_row(
        "Disc% (F_VWAP)",
        "≥ +8% deep (bold green)\n"
        "≥ +3% mid (yellow)\n"
        "≥ +0% shallow (dim)\n"
        "< 0% over (red)",
        (
            "Foreign VWAP discount: how far price is below foreigners' avg cost.\n"
            "Positive = foreigners underwater. Soft triage color only — not a "
            "scoring/ENTER gate. Enrichment / TUI also show deep|mid|shallow|over.\n"
            f"Default list sort is {SIGNAL} high→low (--sort-by signal). "
            f"Use --sort-by score for {ACCUM}, or --sort-by vwap for deepest Disc% first. "
            "--vwap-only keeps Disc% > 0 (excludes over-VWAP)."
        ),
    )
    guide_table.add_row(
        f"{ACCUM} (0–100)",
        "≥ 58 (green)\n33-57 (yellow)\n< 33 (white)",
        (
            f"{ACCUM_DEFINITION}\n"
            "Combines net days, streak, VWAP, RSI, flow-ratio component, and BCI. "
            "BB%ile is setup/phase diagnostic — not in default Accum by default.\n"
            f"- Green: Strong {ACCUM}, worth research.\n"
            f"- Yellow: Moderate watch.\n"
            "- White: Weak, likely noise, skip.\n"
            f"Do not compare {ACCUM} directly to {SIGNAL}."
        )
    )
    guide_table.add_row(
        f"{SIGNAL} (0–100)",
        "STRONG / MODERATE / WEAK",
        (
            f"{SIGNAL_DEFINITION}\n"
            f"Under Signal panel: {SETUP_GRP} and {FLOW_GRP} are group "
            "contributions, not Accum."
        ),
    )
    guide_table.add_row(
        "STREAK",
        "1-2d\n3-4d\n5-7d\n8d+",
        (
            "Consecutive trading days foreigners were net buyers.\n"
            "- 5-7d: Strong, likely intentional.\n"
            "- 8d+: Very strong, committed.\n"
            "Scoring: exponential curve (τ=7d). 7d ≈ 63%, 14d ≈ 86%."
        )
    )
    guide_table.add_row(
        "NET_DAYS",
        "100%\n70-99%\n50-69%\n< 50%",
        (
            "Consistency Ratio (net buy days / total sessions in window).\n"
            "- 100%: Every day was positive buy.\n"
            "- 70-99%: Most days positive.\n"
            "- < 50%: More sells than buys (not accumulating)."
        )
    )
    guide_table.add_row(
        "NET_VALUE",
        "+19.4B\n+10M",
        (
            "Total net foreign flow (buys − sells) in IDR over the window.\n"
            "Confirms real capital size behind the streak.\n"
            "T = trillion | B = billion | M = million (IDR)."
        )
    )
    guide_table.add_row(
        FLOW_RATIO_PCT,
        "0-5%\n5-15%\n15-30%\n30%+",
        (
            f"Average net foreign % of total daily turnover ({ACCUM} component).\n"
            f"Not the same as {ACCUM} total and not {FLOW_GRP} under {SIGNAL}.\n"
            "A mid-cap at 35% FlowRatio is stronger participation than a large-cap at 3%.\n"
            "Scoring: up to 8.3 pts toward Accum, saturates at 20% flow ratio."
        )
    )
    guide_table.add_row(
        "F_VWAP%",
        "> +5% (green)\n+1% to +5%\n< 0%",
        (
            "Foreigners' VWAP to today's close price percentage.\n"
            "- Positive: foreigners bought higher than today's price "
            "(underwater, motivated to defend position).\n"
            "- Negative: foreigners in profit.\n"
            "Scoring: 10% underwater = 16.7 pts."
        )
    )
    guide_table.add_row(
        "RSI (14-day)",
        "> 70\n55-70\n40-55\n25-40\n< 25",
        (
            "Relative Strength Index (0–100).\n"
            "- 25-40: Ideal entry zone.\n"
            "- > 70: Overbought.\n"
            "Scoring: peak at RSI=40 (8.3 pts), zero at RSI≤25 or ≥75."
        )
    )
    guide_table.add_row(
        "BB%ILE",
        "≤ 20% (green)\n21-40% (yellow)\n> 40%",
        (
            "Bollinger Band width percentile vs last 60 days.\n"
            "- ≤ 20%: Squeeze (coiled spring, volatility compressed, "
            "ready to break).\n"
            f"Not scored in default {ACCUM} (setup/structure evidence only)."
        )
    )
    guide_table.add_row(
        "TREND",
        "UP\nDOWN\nSIDE",
        (
            "Price relative to SMA20 (UP = >2% above, DOWN = >2% below, "
            "SIDE = within ±2%).\n"
            "DOWN or SIDE is often ideal to enter before the breakout."
        )
    )
    guide_table.add_row(
        "PATTERN",
        "sustained\nbuilding\nfresh rotation\ncoiled spring",
        (
            "Multi-window 7d/30d/90d evaluation.\n"
            "- sustained: score ≥50 on all windows.\n"
            "- building: strong 7d+30d, weak 90d.\n"
            "- coiled spring: BB squeeze + score ≥50 on any window."
        )
    )
    guide_table.add_row(
        "EVIDENCE PTS",
        "cons / streak / vwap\nrsi / flow / bb / inst",
        (
            "Foreign-flow score components: cons (33.3 pts), streak (25 pts), "
            "vwap (16.7 pts), rsi (8.3 pts), flow (8.3 pts), inst (12.5 pts BCI). "
            "bb shown diagnostically — not scored by default."
        )
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
        "  • Deep-dive: saham view ticker flow <TICKER> --days 30\n"
        "               saham analyze risk <TICKER> --with-sentiment",
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
