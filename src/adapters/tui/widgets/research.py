"""Render-only text helpers for candidate and ticker research screens.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.presenters.accumulation_presenter import (
    AccumulationRowView,
    AccumulationViewModel,
)
from src.adapters.tui.presenters.ticker_research_presenter import (
    TickerResearchViewModel,
)


def _display(value) -> str:
    return "—" if value is None else str(value)


def candidate_label(index: int, row: AccumulationRowView) -> str:
    coverage = "—" if row.signal_coverage is None else f"{row.signal_coverage:.0%}"
    return (
        f"{index + 1:>2}  {row.ticker:<8} {_display(row.next_action):<18} "
        f"{_display(row.signal_score):>3}/{coverage:<4} "
        f"{_display(row.risk):<8} {_display(row.data_state)}"
    )


def candidate_metadata(view: AccumulationViewModel) -> str:
    return "\n".join(f"{label}: {value}" for label, value in view.metadata)


def selected_candidate(row: AccumulationRowView | None) -> str:
    if row is None:
        return "No candidate selected."
    coverage = "—" if row.signal_coverage is None else f"{row.signal_coverage:.0%}"
    return "\n".join(
        (
            row.ticker,
            f"Canonical window: {row.canonical_window} sessions",
            f"Action: {_display(row.next_action)}",
            f"Signal / coverage: {_display(row.signal_score)} / {coverage}",
            f"Risk: {_display(row.risk)}",
            f"Setup phase: {_display(row.setup_phase)}",
            f"Data: {_display(row.data_state)}",
            f"Warning: {_display(row.warning)}",
        )
    )


def research_section(entries: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in entries) or "UNAVAILABLE"


def canonical_verdict(view: TickerResearchViewModel) -> str:
    verdict = view.canonical
    coverage = "—" if verdict.signal_coverage is None else f"{verdict.signal_coverage:.0%}"
    return "\n".join(
        (
            f"Signal status: {verdict.signal_status}",
            f"Unavailable reason: {_display(verdict.unavailable_reason)}",
            f"Action: {_display(verdict.action)}",
            f"Signal / coverage: {_display(verdict.signal_score)} / {coverage}",
            f"Risk: {_display(verdict.risk)}",
            f"Market context: {_display(verdict.regime)}",
        )
    )
