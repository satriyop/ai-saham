"""
Swing analysis display helper functions.

Layer: Adapter
"""

from dataclasses import dataclass
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
        and candidate.score >= config.coiled_spring_min_score
    ):
        return "coiled spring"
    if candidate.score >= config.strong_min_score and candidate.consecutive_streak >= config.strong_min_streak:
        return "strong"
    if candidate.score >= config.building_min_score and candidate.consecutive_streak >= config.building_min_streak:
        return "building"
    if candidate.score >= config.enter_min_score:
        return "high score"
    if candidate.score >= config.watch_min_score:
        return "moderate"
    return "weak"


def format_failed_gates_summary(preset_eval: Any) -> str:
    return "Failed gates: " + "; ".join(preset_eval.failed_reasons)


def swing_summary_parts(
    accum: Any | None,
    risk_resp: Any,
    backtest_result: Any,
    sentiment_resp: Any,
) -> list[str]:
    parts = []
    if accum:
        parts.append(f"Score {accum.score:.1f}")
    if risk_resp:
        parts.append(risk_resp.assessment.risk_level_name)
    if backtest_result and backtest_result.trade_count > 0:
        parts.append(f"{float(backtest_result.win_rate):.0f}% WR")
    if sentiment_resp and not sentiment_resp.warning:
        parts.append(sentiment_resp.snapshot.overall_sentiment.value.lower() + " news")
    return parts


def swing_plan_text(
    ticker: str,
    capital: int | None,
    atr_value: Decimal | None,
    sizing: Any | None,
    preset_eval: Any | None,
    preset_sizing: Any | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
    config: SwingDisplayConfig,
) -> tuple[str, str]:
    strategy_override = (
        strategy_risk_level == "HIGH_RISK"
        and preset_eval is not None
        and preset_eval.passed
    )

    if preset_eval is not None:
        if strategy_override:
            return (
                f"AVOID (strategy gate: '{strategy_risk_name}' signals HIGH_RISK; preset passed but technical signal says exit).",
                "red",
            )
        if preset_eval.passed and preset_sizing and preset_sizing.lots > 0:
            return (
                f"ENTER setup passed. Consider {preset_sizing.lots} lots at "
                f"{float(preset_sizing.entry_price):,.0f}; TP "
                f"{float(preset_sizing.target_price):,.0f}; SL "
                f"{float(preset_sizing.stop_price):,.0f}; max hold "
                f"{config.foreign_bounce_max_hold_days} trading days.",
                "green",
            )
        if preset_eval.passed:
            return ("ENTER setup passed. Add --capital to compute lot size.", "green")
        if preset_eval.classification == "WATCH":
            return (
                "WATCH only. Preset is close but not fully confirmed; wait for failed gates to improve.",
                "yellow",
            )
        return ("AVOID. Preset gates are not aligned.", "red")
    if sizing and sizing.lots > 0:
        return (
            f"Sized scenario: {sizing.lots} lots at {float(sizing.entry_price):,.0f}. "
            f"Stop {float(sizing.stop_price):,.0f}. Target {float(sizing.target_price):,.0f}.",
            "cyan",
        )
    if sizing and sizing.lots == 0:
        return ("Position too small for 1 lot; reduce entry or increase capital.", "red")
    if capital and not atr_value:
        return (
            f"Fetch more data to enable position sizing (run saham fetch market {ticker} --days 90).",
            "yellow",
        )
    return ("No action plan available from current inputs.", "bright_black")


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
