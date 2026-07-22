"""
Formatting and pattern classification helpers for accumulation display.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import typer
from rich.text import Text

from src.application.dto.accumulation_screen import AccumulationCandidate


@dataclass(frozen=True)
class AccumulationDisplayConfig:
    enter_min_foreign_flow_score: float
    watch_min_foreign_flow_score: float
    coiled_spring_min_foreign_flow_score: float
    coiled_spring_bb_pctile: float
    foreign_flow_score_policy: Any


def accumulation_display_config_from_screener(config) -> AccumulationDisplayConfig:
    return AccumulationDisplayConfig(
        enter_min_foreign_flow_score=config.display.enter_min_foreign_flow_score,
        watch_min_foreign_flow_score=config.display.watch_min_foreign_flow_score,
        coiled_spring_min_foreign_flow_score=config.display.coiled_spring_min_foreign_flow_score,
        coiled_spring_bb_pctile=config.display.coiled_spring_bb_pctile,
        foreign_flow_score_policy=config.foreign_flow_score_policy,
    )


_STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}

_PHASE_LABELS = {
    "NONE": "NONE",
    "ACCUMULATION": "ACCUMULATION",
    "COMPRESSION": "COMPRESSION",
    "BREAKOUT_CONFIRMATION": "BREAKOUT",
    "EXHAUSTION": "EXHAUSTION",
    "DISTRIBUTION": "DISTRIBUTION",
    "FAILED": "FAILED",
}

_PHASE_STYLES = {
    "ACCUMULATION": "cyan",
    "COMPRESSION": "yellow",
    "BREAKOUT": "bold green",
    "EXHAUSTION": "yellow",
    "DISTRIBUTION": "red",
    "FAILED": "bold red",
    "NONE": "bright_black",
    "UNKNOWN": "bright_black",
}


def format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def fmt_score(s: float | None, display_config: AccumulationDisplayConfig) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= display_config.enter_min_foreign_flow_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= display_config.watch_min_foreign_flow_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def format_disc_pct(discount: float | None) -> Text:
    """Foreign VWAP discount % with depth color tiers (display-only).

    ≥10 deep, ≥8 strong, ≥3 shallow, else dim / missing.
    """
    if discount is None:
        return Text("—", style="bright_black")
    label = f"{discount:+.1f}%"
    if discount >= 10.0:
        return Text(label, style="bold green")
    if discount >= 8.0:
        return Text(label, style="green")
    if discount >= 3.0:
        return Text(label, style="yellow")
    return Text(label, style="bright_black")


def classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, AccumulationCandidate | None],
    display_config: AccumulationDisplayConfig,
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = display_config.coiled_spring_min_foreign_flow_score
    hot = [
        w for w in windows
        if candidates_by_window.get(w) and candidates_by_window[w].foreign_flow_score >= threshold
    ]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if (
            c
            and c.foreign_flow_score >= threshold
            and c.bb_width_pctile is not None
            and c.bb_width_pctile <= display_config.coiled_spring_bb_pctile
        ):
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"


def notation_label(snapshot) -> str:
    if snapshot is None:
        return "-"
    parts = []
    if getattr(snapshot, "codes", None):
        parts.append(",".join(snapshot.codes))
    if getattr(snapshot, "tradeable", None) is False:
        parts.append("NO-TRADE")
    status = getattr(snapshot, "status", None)
    if status and status != "STATUS_ACTIVE":
        parts.append(status.replace("STATUS_", ""))
    if getattr(snapshot, "suspend_info", None):
        parts.append("SUSP")
    if getattr(snapshot, "has_uma", None):
        parts.append("UMA")
    return "+".join(parts) if parts else "-"


def notation_detail(snapshot) -> str:
    if snapshot is None:
        return ""
    bits = []
    label = notation_label(snapshot)
    if label != "-":
        bits.append(label)
    if snapshot.listing_board:
        bits.append(snapshot.listing_board)
    if snapshot.haircut_percentage:
        bits.append(f"haircut={snapshot.haircut_percentage}")
    return " | ".join(bits)


def _phase_cell(setup_phase) -> Text:
    """Render the accumulation-lifecycle phase diagnostic for a candidate row.

    setup_phase is None when detection was unavailable or failed — displayed as
    UNKNOWN, distinct from a successfully-detected SetupPhaseState.NONE.
    """
    if setup_phase is None:
        return Text("UNKNOWN", style=_PHASE_STYLES["UNKNOWN"])
    label = _PHASE_LABELS.get(setup_phase.current_phase.value, "UNKNOWN")
    return Text(label, style=_PHASE_STYLES.get(label, ""))


def _price_text(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def _risk_reason(assessment) -> str:
    if assessment is None or not assessment.rationale:
        return "-"
    return "; ".join(assessment.rationale)


def _risk_tier(assessment) -> str:
    if assessment is None or not assessment.gate_triggered:
        return "-"
    return "structural" if assessment.gate_is_structural else "execution"


def _risk_detail_line(rank: int, candidate: AccumulationCandidate) -> Text:
    assessment = candidate.risk_assessment
    if assessment is None:
        return Text(f"#{rank} {candidate.ticker}: risk unavailable", style="dim")
    if not assessment.gate_triggered:
        return Text(f"#{rank} {candidate.ticker}: no risk gate fired", style="dim")
    reason = _risk_reason(assessment)
    return Text(
        f"#{rank} {candidate.ticker}: {assessment.gate_triggered} - {reason}",
        style="red" if assessment.gate_is_structural else "yellow",
    )


_ALIGNMENT_LABELS = {
    "ALIGNED": "Aligned",
    "LAG": "Lag",
    "MISSING": "Missing",
    "UNKNOWN": "Unknown",
}

_READINESS_LABELS = {
    "READY": "Ready",
    "PENDING_EOD": "Pending EOD",
    "STALE": "Stale",
    "PARTIAL": "Partial",
    "MISSING": "Missing",
    "UNKNOWN": "Unknown",
}


def _alignment_text(candidate: AccumulationCandidate) -> str:
    """Source-equality label: candle date == broker date? Distinct from
    readiness — alignment alone does not mean the data is current."""
    if candidate.freshness is None:
        return _ALIGNMENT_LABELS["UNKNOWN"]
    return _ALIGNMENT_LABELS[candidate.freshness.alignment_state.value]


def _readiness_text(candidate: AccumulationCandidate) -> str:
    """Worst-of(candle_state, broker_state) — is the data current for the
    expected latest IDX EOD session?"""
    if candidate.freshness is None:
        return _READINESS_LABELS["UNKNOWN"]
    order = ["MISSING", "STALE", "UNKNOWN", "PARTIAL", "PENDING_EOD", "READY"]
    states = [
        candidate.freshness.candle_state.value,
        candidate.freshness.broker_state.value,
    ]
    worst = min(states, key=order.index)
    return _READINESS_LABELS[worst]


def _coverage_text(candidate: AccumulationCandidate) -> str:
    if candidate.freshness is None or candidate.freshness.signal_evidence_coverage is None:
        return "-"
    return f"{candidate.freshness.signal_evidence_coverage:.0%}"
