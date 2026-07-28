"""Display helpers for `saham assess pre-open`.

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.dto.assess_pre_open import AssessPreOpenResult


def result_to_json_dict(result: AssessPreOpenResult) -> dict[str, Any]:
    """Stdout JSON payload (no file write)."""
    return {
        "artifact_type": "assess_pre_open_result",
        "session_date": result.session_date.isoformat(),
        "status": result.status.value,
        "market_regime": result.market_regime,
        "max_stop_pct": str(result.max_stop_pct),
        "warnings": list(result.warnings),
        "policy_identity": dict(result.policy_identity),
        "lines": [
            {
                "observation_id": line.observation_id,
                "opening_snapshot_id": line.opening_snapshot_id,
                "ticker": line.ticker,
                "pre_open": dict(line.pre_open),
                "post_open_action": line.confirmation.decision.value,
                "opening_price": (
                    str(line.confirmation.opening_price)
                    if line.confirmation.opening_price is not None
                    else None
                ),
                "planned_entry": (
                    str(line.confirmation.planned_entry)
                    if line.confirmation.planned_entry is not None
                    else None
                ),
                "stop_loss_price": (
                    str(line.confirmation.stop_loss_price)
                    if line.confirmation.stop_loss_price is not None
                    else None
                ),
                "stop_pct": (
                    str(line.confirmation.stop_pct)
                    if line.confirmation.stop_pct is not None
                    else None
                ),
                "reasons": list(line.confirmation.reasons),
                "price_provenance": dict(line.price_provenance),
                "cutoff_at": line.cutoff_at.isoformat(),
                "compatibility_id": line.compatibility_id,
                "contract_id": line.contract_id,
            }
            for line in result.lines
        ],
    }


def _short_id(value: str | None) -> str:
    if not value:
        return "-"
    if len(value) <= 13:
        return value
    return value[:12] + "…"


def display_assess_pre_open(result: AssessPreOpenResult) -> None:
    """Rich table: pre-open state vs post-open action."""
    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Session", result.session_date.isoformat())
    summary.add_row("Status", result.status.value)
    summary.add_row("Market regime", result.market_regime or "-")
    summary.add_row("Tickers", str(len(result.lines)))
    summary.add_row("Max stop", f"{result.max_stop_pct:.2%}")
    summary.add_row(
        "Next",
        "saham trade pre-open log --observation-id … --opening-snapshot-id …",
    )

    table = compact_table()
    table.add_column("Ticker", style="bold")
    table.add_column("Pre-open", style="cyan")
    table.add_column("Post-open", style="bold")
    table.add_column("Open", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Stop", justify="right")
    table.add_column("Source")
    table.add_column("observation_id")
    table.add_column("opening_snapshot_id")
    table.add_column("Reason")

    for line in result.lines:
        c = line.confirmation
        pre = line.pre_open
        setup = (
            pre.get("setup_action") or pre.get("entry_quality") or pre.get("screen_result") or "-"
        )
        direction = pre.get("direction") or pre.get("trend_signal") or "-"
        pre_label = f"{setup}/{direction}"
        open_px = f"{c.opening_price:,.0f}" if c.opening_price is not None else "-"
        entry = f"{c.planned_entry:,.0f}" if c.planned_entry is not None else "-"
        stop = f"{c.stop_loss_price:,.0f}" if c.stop_loss_price is not None else "-"
        source = line.price_provenance.get("opening_price_source") or c.opening_price_source or "-"
        reason = "; ".join(c.reasons) if c.reasons else "-"
        table.add_row(
            line.ticker,
            pre_label,
            c.decision.value,
            open_px,
            entry,
            stop,
            str(source),
            _short_id(line.observation_id),
            _short_id(line.opening_snapshot_id),
            reason[:60],
        )

    sections: list[Any] = [
        Text(
            "Post-open assessment of NCP pre-open plan (read-only)",
            style="bold cyan",
        ),
        summary,
        Text("Decisions", style="bold cyan"),
        table,
    ]
    if result.warnings:
        sections.append(Text("Warnings: " + " | ".join(result.warnings), style="yellow"))

    console().print(panel(Group(*sections), title="ANALYZE PRE-OPEN"))


def echo_json(result: AssessPreOpenResult) -> None:
    import typer

    typer.echo(json.dumps(result_to_json_dict(result), indent=2))
