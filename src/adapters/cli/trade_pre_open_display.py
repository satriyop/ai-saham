"""
Display helpers for pre-open post-open assess and paper journal CLI output.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.resolve_opening_prices_use_case import OpeningPriceObservation
from src.domain.value_objects.pre_open_post_open_assessment import PreOpenPostOpenAssessment


def format_ticker_preview(tickers: list[str], *, limit: int = 8) -> str:
    if len(tickers) <= limit:
        return ", ".join(tickers)
    return ", ".join(tickers[:limit]) + f", ... (+{len(tickers) - limit} more)"


def fmt_price(value: Decimal | None) -> str:
    return f"{value:,.0f}" if value is not None else "-"


def fmt_signed_decimal(value: Decimal | None, suffix: str = "") -> str:
    return f"{value:+.2f}{suffix}" if value is not None else "-"


def format_opening_observation_status(
    index: int,
    total: int,
    observation: OpeningPriceObservation,
) -> str:
    prefix = f"[{index}/{total}] {observation.ticker}"
    if observation.price is not None:
        source = observation.source or "unknown"
        return (
            f"{prefix}: {fmt_price(observation.price)} "
            f"via {source}/{observation.confidence}"
        )
    reason = observation.reason or "unresolved"
    return f"{prefix}: unresolved - {reason}"


def display_pre_open_post_open_assessments(
    confirmations: tuple[PreOpenPostOpenAssessment, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    extras: dict[str, dict] | None = None,
) -> None:
    extras = extras or {}

    if not confirmations:
        empty = compact_table(show_header=False)
        empty.add_column("Label")
        empty.add_column("Value")
        empty.add_row("Date", confirmed_date.isoformat())
        empty.add_row("Candidates", "0")
        empty.add_row("Next", "Run saham screen pre-open first")
        console().print(panel(empty, title="PRE-OPEN POST-OPEN ASSESS"))
        return

    enters = [c for c in confirmations if c.decision.value == "ENTER"]
    waits = [c for c in confirmations if c.decision.value == "WAIT"]
    skips = [c for c in confirmations if c.decision.value not in ("ENTER", "WAIT")]

    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Date", confirmed_date.isoformat())
    summary.add_row("Candidates", str(len(confirmations)))
    summary.add_row("ENTER", str(len(enters)))
    summary.add_row("WAIT", str(len(waits)))
    summary.add_row("SKIP", str(len(skips)))
    summary.add_row("Max stop", f"{max_stop_pct:.2%}")
    summary.add_row(
        "Next",
        "saham trade pre-open log --observation-id … --opening-snapshot-id …",
    )

    sections = [Text("Session Summary", style="bold cyan"), summary]

    def add_decision_table(title: str, rows: list[PreOpenPostOpenAssessment]) -> None:
        if not rows:
            return
        table = compact_table()
        table.add_column("Ticker", style="bold")
        table.add_column("Open", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Stop", justify="right")
        table.add_column("Stop%", justify="right")
        table.add_column("Source")
        table.add_column("Reason")
        for confirmation in rows:
            ex = extras.get(confirmation.ticker, {})
            source = ex.get("opening_price_source") or confirmation.opening_price_source or "-"
            confidence = ex.get("opening_price_confidence") or confirmation.opening_price_confidence
            source_text = f"{source}/{confidence}" if confidence else source
            reason = (
                confirmation.reasons[-1]
                if confirmation.reasons
                else confirmation.decision.value.lower().replace("_", " ")
            )
            table.add_row(
                confirmation.ticker,
                fmt_price(confirmation.opening_price),
                fmt_price(confirmation.planned_entry),
                fmt_price(confirmation.stop_loss_price),
                fmt_signed_decimal(confirmation.stop_pct, "%"),
                source_text,
                reason,
            )
        sections.extend([Text(title, style="bold"), table])

    add_decision_table("ENTER - act now", enters)
    add_decision_table("WAIT - monitor first 15 min", waits)
    add_decision_table("SKIP - do not enter", skips)

    unresolved = [c.ticker for c in confirmations if c.opening_price is None]
    if unresolved:
        warning_table = compact_table(show_header=False)
        warning_table.add_column("Warning")
        warning_table.add_row(
            "Unresolved opening prices: " + format_ticker_preview(unresolved)
        )
        sections.extend([Text("Warnings", style="bold yellow"), warning_table])

    console().print(
        panel(
            Group(*sections),
            title="PRE-OPEN POST-OPEN ASSESS",
            subtitle=confirmed_date.isoformat(),
        )
    )


def display_pre_open_paper_review(report, journal_path: Path) -> None:
    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row("Journal", str(journal_path))
    summary.add_row("Total logged entries", str(report.total_entries))
    summary.add_row("Entries with outcome", str(report.entries_with_data))

    if report.total_entries == 0:
        summary.add_row(
        "Next",
        "saham trade pre-open log --observation-id … --opening-snapshot-id …",
    )
        console().print(panel(summary, title="PRE-OPEN PAPER JOURNAL REVIEW"))
        return

    sections = [Text("Review Summary", style="bold cyan"), summary]

    def add_bucket_table(title: str, rows) -> None:
        if not rows:
            return
        table = compact_table()
        table.add_column("Bucket", style="bold")
        table.add_column("Total", justify="right")
        table.add_column("Data", justify="right")
        table.add_column("ENTER", justify="right")
        table.add_column("UP", justify="right")
        table.add_column("STOP", justify="right")
        table.add_column("TGT1R", justify="right")
        table.add_column("Avg R", justify="right")
        for row in rows:
            avg_r = f"{row.avg_close_r:+.2f}" if row.avg_close_r is not None else "-"
            table.add_row(
                row.bucket,
                str(row.total),
                str(row.with_data),
                str(row.enter_count),
                str(row.up_count),
                str(row.stop_hit_count),
                str(row.target_1r_hit_count),
                avg_r,
            )
        sections.extend([Text(title, style="bold"), table])

    add_bucket_table("By decision", report.decision_buckets)
    for label, rows in report.context_buckets.items():
        add_bucket_table(f"By {label}", rows)

    sections.append(
        Text(
            "Note: manual outcomes are used first. Rows without manual outcomes use "
            "daily OHLC as a proxy; exact intraday sequence requires minute/tick data.",
            style="dim",
        )
    )
    console().print(
        panel(
            Group(*sections),
            title="PRE-OPEN PAPER JOURNAL REVIEW",
        )
    )
