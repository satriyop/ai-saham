"""
Multi-window display rendering for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.screen_accum_formatters import AccumulationDisplayConfig, classify_pattern
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)


def display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: date,
    display_config: AccumulationDisplayConfig,
    broker_quality = None,
    include_explanation: bool = False,
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
            tk: pw
            for tk, pw in by_ticker.items()
            if any(
                c.bb_width_pctile is not None
                and c.bb_width_pctile <= display_config.coiled_spring_bb_pctile
                for c in pw.values()
            )
        }

    def sort_key(item: tuple) -> float:
        pw = item[1]
        scores = [c.foreign_flow_score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        try:
            w = int(sort_by.rstrip("ds"))
            c = pw.get(w)
            return c.foreign_flow_score if c else 0.0
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
    table.add_column("Broker Flow")

    for i, (tk, pw) in enumerate(rows, 1):
        score_cells = []
        for w in windows:
            candidate = pw.get(w)
            if candidate is None:
                score_cells.append(Text("—", style="bright_black"))
                continue
            style = "green" if candidate.foreign_flow_score >= (
                display_config.enter_min_foreign_flow_score
            ) else (
                "yellow" if candidate.foreign_flow_score >= (
                    display_config.watch_min_foreign_flow_score
                ) else ""
            )
            score_cells.append(Text(f"{candidate.foreign_flow_score:.0f}", style=style))
        pattern = classify_pattern(windows, pw, display_config)
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

    if not include_explanation:
        return

    # Render run context cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    sample_resp = next(iter(results.values()))
    meta_table.add_row(
        "Stats",
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )

    enter_score = display_config.enter_min_foreign_flow_score
    watch_score = display_config.watch_min_foreign_flow_score
    meta_table.add_row(
        "Scores",
        f"Accum ≥{enter_score:g} green | ≥{watch_score:g} yellow | <{watch_score:g} white"
    )

    meta_table.add_row(
        "Patterns",
        "sustained | building | fresh rotation | long-term only | coiled spring | weak"
    )

    meta_table.add_row(
        "Broker Flow",
            "5-session named top-broker bucket: "
            "smart+/noise+ = net buying, smart-/noise- = net selling, n/a = no detail"
    )

    meta_table.add_row(
        "Disclaimer",
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Run Context",
        )
    )
