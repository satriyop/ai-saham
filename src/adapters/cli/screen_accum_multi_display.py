"""
Multi-window display rendering for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.screen_accum_formatters import AccumulationDisplayConfig
from src.application.services.screen_accum_result_projector import ScreenAccumMultiRow


def display_multi(
    rows: list[ScreenAccumMultiRow],
    universe_label: str,
    windows: list[int],
    screened_at: date,
    display_config: AccumulationDisplayConfig,
    total_tickers_checked: int = 0,
    provider: str = "",
    include_explanation: bool = False,
) -> None:
    """Render multi-window side-by-side table.

    `rows` are the already-filtered/sorted/limited projection from
    src.application.services.screen_accum_result_projector — this function
    must not independently filter, sort, or slice.
    """
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

    for i, row in enumerate(rows, 1):
        score_cells = []
        for w in windows:
            candidate = row.candidates_by_window.get(w)
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
        brk = row.broker_quality.label if row.broker_quality else "n/a"
        table.add_row(str(i), row.ticker, *score_cells, row.pattern, row.trend, brk)

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

    meta_table.add_row(
        "Stats",
        f"Checked: {total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {provider}"
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
