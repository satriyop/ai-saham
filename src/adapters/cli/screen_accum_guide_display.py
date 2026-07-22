"""
Column guide display for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel


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
        "horizon).\n",
        style="italic"
    )

    # Aligned Guide Table
    guide_table = compact_table()
    guide_table.add_column("Signal / Metric", style="bold yellow", width=22)
    guide_table.add_column("Value / Bench", style="cyan", width=20)
    guide_table.add_column("Details & Mechanics")

    guide_table.add_row(
        "Disc% (F_VWAP)",
        "≥ +10% deep\n≥ +8% strong\n≥ +3% shallow\nelse dim",
        (
            "Foreign VWAP discount: how far price is below foreigners' avg cost.\n"
            "Positive = foreigners underwater. Default list sort is deepest Disc% first "
            "(--sort-by vwap). Use --sort-by score to rank by Accum score instead."
        ),
    )
    guide_table.add_row(
        "SCORE (0–100)",
        "≥ 58 (green)\n33-57 (yellow)\n< 33 (white)",
        (
            "Composite signal strength. Combines net days, streak, VWAP, RSI, "
            "flow, and BCI into a single score. BB%ile is shown as setup/phase "
            "diagnostic — it does not contribute to foreign-flow score by default.\n"
            "- Green: Strong signal, worth research.\n"
            "- Yellow: Moderate watch, wait for confirmation.\n"
            "- White: Weak, likely noise, skip."
        )
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
        "FLOW%",
        "0-5%\n5-15%\n15-30%\n30%+",
        (
            "Average net foreign % of total daily turnover.\n"
            "A mid-cap at 35% FLOW% is a stronger signal than a large-cap at 3%.\n"
            "Scoring: up to 8.3 pts, saturates at 20% flow ratio."
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
            "Not scored in default foreign-flow score (setup/structure evidence only)."
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
        "  • Deep-dive: saham view broker flow <TICKER> --days 30\n"
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
