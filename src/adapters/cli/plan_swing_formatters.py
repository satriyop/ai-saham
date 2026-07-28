"""
Pure formatting/style helpers for saham plan swing display modules.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import typer


@dataclass(frozen=True)
class SwingDisplayConfig:
    enter_min_score: float
    watch_min_score: float
    coiled_spring_bb_pctile: float
    coiled_spring_min_score: float
    strong_min_score: float
    strong_min_streak: int
    building_min_score: float
    building_min_streak: int
    foreign_bounce_max_hold_days: int


def fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "missing"


def sep(char: str = "=", width: int = 70) -> None:
    typer.echo(char * width)


def style_risk(level: str) -> str:
    if level == "LOW_RISK":
        return typer.style(level, fg=typer.colors.GREEN, bold=True)
    if level == "HIGH_RISK":
        return typer.style(level, fg=typer.colors.RED, bold=True)
    return typer.style(level, fg=typer.colors.YELLOW, bold=True)


def style_trend(trend: str) -> str:
    if trend == "UP":
        return typer.style(trend, fg=typer.colors.GREEN)
    if trend == "DOWN":
        return typer.style(trend, fg=typer.colors.RED)
    return typer.style(trend, fg=typer.colors.YELLOW)


def style_sentiment_call(call: str) -> str:
    if call == "POSITIVE":
        return typer.style(call, fg=typer.colors.GREEN, bold=True)
    if call == "NEGATIVE":
        return typer.style(call, fg=typer.colors.RED, bold=True)
    return typer.style(call, fg=typer.colors.YELLOW, bold=True)


def style_score(score: float, config: SwingDisplayConfig) -> str:
    if score >= config.enter_min_score:
        return typer.style(f"{score:.1f}", fg=typer.colors.GREEN, bold=True)
    if score >= config.watch_min_score:
        return typer.style(f"{score:.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{score:.1f}", fg=typer.colors.WHITE)


def style_bb(pctile: float) -> str:
    pct_int = int(pctile * 100)
    if pctile <= 0.20:
        return typer.style(f"{pct_int}%", fg=typer.colors.GREEN)
    if pctile <= 0.40:
        return typer.style(f"{pct_int}%", fg=typer.colors.YELLOW)
    return f"{pct_int}%"


def style_winrate(win_rate: Decimal) -> str:
    value = float(win_rate)
    if value >= 55:
        return typer.style(f"{value:.1f}%", fg=typer.colors.GREEN)
    if value >= 45:
        return typer.style(f"{value:.1f}%", fg=typer.colors.YELLOW)
    return typer.style(f"{value:.1f}%", fg=typer.colors.RED)


def style_gate(passed: bool) -> str:
    label = "PASS" if passed else "FAIL"
    color = typer.colors.GREEN if passed else typer.colors.RED
    return typer.style(label, fg=color, bold=True)


def style_setup_match(value: str) -> str:
    if value == "MATCH":
        return typer.style(value, fg=typer.colors.GREEN, bold=True)
    if value == "PARTIAL":
        return typer.style(value, fg=typer.colors.YELLOW, bold=True)
    return typer.style(value, fg=typer.colors.RED, bold=True)


def section_header(title: str, right: str = "", width: int = 70) -> None:
    styled = typer.style(title, bold=True)
    if right:
        gap = max(1, width - len(title) - len(right) - 2)
        typer.echo(f"{styled}{' ' * gap}{right}")
    else:
        typer.echo(styled)


def signal_label(candidate: Any, config: SwingDisplayConfig) -> str:
    if (
        candidate.bb_width_pctile is not None
        and candidate.bb_width_pctile <= config.coiled_spring_bb_pctile
        and candidate.accum_score >= config.coiled_spring_min_score
    ):
        return "coiled spring"
    if (
        candidate.accum_score >= config.strong_min_score
        and candidate.consecutive_streak >= config.strong_min_streak
    ):
        return "strong"
    if (
        candidate.accum_score >= config.building_min_score
        and candidate.consecutive_streak >= config.building_min_streak
    ):
        return "building"
    if candidate.accum_score >= config.enter_min_score:
        return "high score"
    if candidate.accum_score >= config.watch_min_score:
        return "moderate"
    return "weak"


def foreign_flow_evidence_label(candidate: Any, config: SwingDisplayConfig) -> str:
    foreign_flow_evidence = getattr(candidate, "foreign_flow_evidence", None)
    status = getattr(foreign_flow_evidence, "confirmation_status", None)
    if status:
        return str(status).lower().replace("_", "-")
    if candidate.accum_score >= config.enter_min_score:
        return "enter-zone"
    if candidate.accum_score >= config.watch_min_score:
        return "watch-zone"
    return "weak"


def flow_direction_label(candidate: Any) -> str:
    foreign_flow_evidence = getattr(candidate, "foreign_flow_evidence", None)
    direction = getattr(foreign_flow_evidence, "flow_direction", None)
    if direction:
        return f"flow {str(direction).lower()}"
    flow = getattr(candidate, "avg_flow_ratio", None)
    if flow is None:
        return "flow unknown"
    if flow > 0:
        return "flow positive"
    if flow < 0:
        return "flow negative"
    return "flow flat"


def notation_label(snapshot: Any) -> str:
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


def notation_detail(snapshot: Any) -> str:
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


def swing_summary_parts(
    accum: Any | None,
    risk_resp: Any,
    backtest_result: Any,
    sentiment_resp: Any,
) -> list[str]:
    parts = []
    if accum:
        parts.append(f"Foreign Flow Score {accum.accum_score:.1f}")
    if risk_resp and risk_resp.assessment.gate_triggered:
        parts.append(f"gate: BLOCKED ({risk_resp.assessment.gate_triggered})")
    if backtest_result and backtest_result.trade_count > 0:
        parts.append(f"{float(backtest_result.win_rate):.0f}% WR")
    if sentiment_resp and not sentiment_resp.warning:
        parts.append(sentiment_resp.snapshot.overall_sentiment.value.lower() + " news")
    return parts


def _fmt_pct_compare(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"
