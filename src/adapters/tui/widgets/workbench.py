"""Render-only text helpers for the Ticker Decision Workbench.

These format an already-computed ``TickerWorkbenchViewModel``. They perform no
indicator, sizing, verdict, or setup-fit calculation — that authority stays in the
application layer and the presenter.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.presenters.ticker_workbench_presenter import (
    DecisionStripView,
    TickerWorkbenchViewModel,
)


def _display(value) -> str:
    return "—" if value is None else str(value)


def rows_text(rows: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in rows) or "— UNAVAILABLE"


def verdict_line(decision: DecisionStripView) -> str:
    """The single strongest line: canonical action badge first, always."""
    coverage = "—" if decision.signal_coverage is None else f"{decision.signal_coverage:.0%}"
    return (
        f"{decision.badge.symbol} {decision.badge.text}"
        f"   Signal {_display(decision.signal_score)}/{coverage}"
        f"   Risk {_display(decision.risk)}"
        f"   Setup {_display(decision.setup_match)}"
    )


def blockers_line(decision: DecisionStripView) -> str:
    if not decision.blockers:
        return "BLOCKERS  none"
    return "BLOCKERS  " + ", ".join(decision.blockers)


def header_line(decision: DecisionStripView, *, mode_label: str) -> str:
    return (
        f"{decision.ticker}   Signal status {decision.signal_status}"
        f"   Setup [{_display(decision.setup_name)}]   Mode [{mode_label}]"
    )


def overview_body(view: TickerWorkbenchViewModel) -> str:
    warnings = "\n".join(view.warnings) if view.warnings else "No warnings."
    return "\n".join(
        (
            "CANONICAL",
            verdict_line(view.decision),
            blockers_line(view.decision),
            f"Market context: {_display(view.decision.regime)}",
            "",
            "EVIDENCE",
            rows_text(view.overview),
            "",
            "WARNINGS",
            warnings,
        )
    )


def setup_body(view: TickerWorkbenchViewModel) -> str:
    decision = view.decision
    return "\n".join(
        (
            f"Selected setup: {_display(decision.setup_name)}",
            f"Setup fit: {_display(decision.setup_match)}  (fit is evidence, not the action)",
            "",
            "GATES / SETUP EVIDENCE",
            rows_text(view.setup),
        )
    )


def signal_risk_body(view: TickerWorkbenchViewModel) -> str:
    return "\n".join(
        (
            "SIGNAL & RISK",
            rows_text(view.signal_risk),
            "",
            "⚡ NON-CANONICAL PREVIEW",
            rows_text(view.preview),
        )
    )
