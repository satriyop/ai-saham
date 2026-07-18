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
from src.application.services.tracked_broker_flow import TrackedBrokerFlowSnapshot


def _tracked_broker_flow_cell(tracked_broker_flow: TrackedBrokerFlowSnapshot | None) -> str:
    """Render only the tracked-broker-subset flow — never the real data
    source (e.g. idx/stockbit), since this is not full-market broker
    composition and must not read like it is."""
    if tracked_broker_flow is None:
        return "N/A"
    return f"{tracked_broker_flow.label} tracked/{tracked_broker_flow.sessions}s"


def display_multi(
    rows: list[ScreenAccumMultiRow],
    universe_label: str,
    windows: list[int],
    screened_at: date,
    display_config: AccumulationDisplayConfig,
    total_tickers_checked: int = 0,
    provider: str = "",
    include_explanation: bool = False,
    canonical_window: int = 7,
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
    table.add_column("Signal/Auth")
    table.add_column("Risk")
    table.add_column("Phase")
    table.add_column("Data")
    table.add_column("Next")
    table.add_column("Tracked Broker Flow")

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

        if row.signal_score is not None and row.signal_authority_coverage is not None:
            signal_cell = f"{row.signal_score:.0f}/{row.signal_authority_coverage:.2f}"
        elif row.signal_score is not None:
            signal_cell = f"{row.signal_score:.0f}"
        else:
            signal_cell = "N/A"

        risk_cell = row.risk_status or "N/A"
        phase_cell = row.setup_phase or "N/A"
        data_cell = row.data_status or "N/A"
        next_cell = row.next_action or "N/A"

        brk = _tracked_broker_flow_cell(row.tracked_broker_flow)
        table.add_row(
            str(i),
            row.ticker,
            *score_cells,
            row.pattern,
            signal_cell,
            risk_cell,
            phase_cell,
            data_cell,
            next_cell,
            brk,
        )

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

    meta_table.add_row(
        "Signal/Auth",
        "score / signal authority coverage from the canonical window"
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
        "Tracked Broker Flow",
        "Tracked Broker Flow uses configured tracked brokers from broker_daily_flow. "
        "It is not full-market broker composition. "
        "smart+/noise+ = net buying, smart-/noise- = net selling, N/A = no detail"
    )

    meta_table.add_row(
        "Canonical Window",
        f"{canonical_window} sessions — Signal/Risk/Phase/Data/Next come "
        "from the canonical window only; other windows are flow context."
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
