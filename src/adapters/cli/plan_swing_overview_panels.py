"""
Panel builders for saham plan swing structure-first overview (ADR-054 S4).

Owns per-section Rich panel construction (Structure, Signal, Risk, Market,
Data) and the label/style/detail helpers that feed them.
print_swing_rich_overview() owns assembly and printing.


Layer: Adapter

This module renders facts already produced by application/domain. It must
not compute business action, and must not introduce or alter thresholds.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_formatters import fmt_date, notation_detail
from src.adapters.cli.rich_display import compact_table, panel
from src.application.dto.plan_swing import (
    ScreenJudgmentReference,
    ScreenJudgmentStatus,
)


def _signal_label(
    signal_assessment: Any | None,
    availability: ScreenJudgmentReference,
) -> tuple[str, str, str]:
    if not isinstance(availability, ScreenJudgmentReference):
        raise TypeError("availability must be a ScreenJudgmentReference")

    if availability.status is ScreenJudgmentStatus.UNAVAILABLE:
        reason_str = (
            availability.unavailable_reason.value if availability.unavailable_reason else "unknown"
        )
        reason_display = reason_str.replace("_", " ")
        return "N/A", "bright_black", f"signal unavailable: {reason_display}"

    if signal_assessment is None:
        return "N/A", "white", "signal unavailable"
    assessment = signal_assessment.assessment
    style = {
        "STRONG": "bold green",
        "MODERATE": "yellow",
        "WEAK": "red",
    }.get(assessment.strength.value, "white")
    return (
        assessment.strength.value,
        style,
        f"score {assessment.score:.1f}; {assessment.entry_quality.value}",
    )


def _build_signal_panel(
    signal_assessment: Any | None,
    availability: ScreenJudgmentReference,
) -> Any:
    if not isinstance(availability, ScreenJudgmentReference):
        raise TypeError("availability must be a ScreenJudgmentReference")

    if availability.status is ScreenJudgmentStatus.UNAVAILABLE:
        reason_str = (
            availability.unavailable_reason.value if availability.unavailable_reason else "unknown"
        )
        reason_display = reason_str.replace("_", " ")
        return panel(Text(f"Signal unavailable: {reason_display}", style="dim red"), title="Signal")

    if signal_assessment is None:
        return panel(Text("Signal unavailable", style="dim"), title="Signal")

    assessment = signal_assessment.assessment
    strength_value, strength_style, _ = _signal_label(signal_assessment, availability)
    coverage_score = assessment.signal_authority_coverage

    headline_table = compact_table(show_header=False)
    headline_table.add_column("Strength")
    headline_table.add_column("Score")
    headline_table.add_column("Spacer")
    headline_table.add_row(
        Text(strength_value, style=strength_style),
        (
            f"score {assessment.score:.1f}  "
            f"cov {coverage_score:.0%}  "
            f"{assessment.entry_quality.value}"
        ),
        "",
    )

    items = [headline_table]

    breakdown = getattr(assessment, "breakdown_dict", None) or {}
    active_flags = getattr(signal_assessment, "active_flags", ())
    _flag_abbr = {
        "VALUATION_STRETCHED": "VAL",
        "ANALYST_BEARISH": "ANL",
        "INSIDER_SELLING": "INS",
    }
    if breakdown:
        key_map = [
            ("setup_quality_group", "Setup", False),
            ("flow_confirmation_group", "Flow", False),
            ("signal_authority_coverage", "Cov%", True),
        ]
        factor_table = compact_table()
        for _, header, _ in key_map:
            factor_table.add_column(header, justify="right")
        factor_table.add_column("Flags")
        factor_table.add_row(
            *(
                (
                    (f"{breakdown[key]:.0f}%" if is_pct else str(round(breakdown[key])))
                    if key in breakdown
                    else "-"
                )
                for key, _, is_pct in key_map
            ),
            " ".join(_flag_abbr.get(f, f[:3]) for f in active_flags) or "-",
        )
        items.append(factor_table)

    constraints = getattr(assessment, "decision_constraints", None)
    if constraints is not None:
        reasons = list(getattr(constraints, "constraint_reasons", ()) or ())
        detail = (
            f"max {constraints.max_decision}; size x{constraints.effective_size_multiplier:.2f}"
        )
        if constraints.regime:
            detail = f"{constraints.regime}; " + detail
        if reasons:
            detail += f"; {reasons[0]}"
        items.append(Text(detail, style="dim"))

    return panel(Group(*items), title="Signal")


def _build_plan_panel(plan_text, plan_style, capital, chosen_sizing) -> Any:
    """Legacy Plan panel — prefer structure panel (ADR-054 S4)."""
    if not capital or chosen_sizing is None:
        return panel(Text(plan_text, style=f"bold {plan_style}"), title="Structure")

    table = compact_table(show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Next step", Text(plan_text, style=f"bold {plan_style}"))
    table.add_row(
        "Sizing",
        f"Entry {float(chosen_sizing.entry_price):,.0f} | "
        f"Stop {float(chosen_sizing.stop_price):,.0f} | "
        f"Target {float(chosen_sizing.target_price):,.0f} | "
        f"Lots {chosen_sizing.lots:,} | "
        f"Capital {capital:,.0f}",
    )
    return panel(table, title="Structure")


def _build_structure_panel(
    *,
    action_value: str,
    action_style: str,
    action_detail: str,
    price: str,
    plan_text: str,
    plan_style: str,
    capital: int | None,
    chosen_sizing: Any,
    setup_value: str,
    setup_style: str,
    ticker: str,
) -> Any:
    """ADR-054 S4: structure desk headline (entry/stop/target/lots + Action)."""
    table = compact_table(show_header=False)
    table.add_column("Key", style="bold cyan", width=14)
    table.add_column("Value")
    table.add_row("Action", Text(action_value, style=action_style))
    table.add_row(
        "Action source",
        "screen judgment (always) · plan never recomputes Action (policy A)",
    )
    if action_detail:
        table.add_row("Why", action_detail[:160] + ("…" if len(action_detail) > 160 else ""))
    table.add_row("Horizon", "swing (multi-day)")
    table.add_row("Price / entry ref", price)
    table.add_row("Setup lens", Text(setup_value, style=setup_style))

    if capital and chosen_sizing is not None:
        table.add_row("Entry", f"{float(chosen_sizing.entry_price):,.0f}")
        table.add_row("Stop", f"{float(chosen_sizing.stop_price):,.0f}")
        table.add_row("Target", f"{float(chosen_sizing.target_price):,.0f}")
        table.add_row("Lots", f"{chosen_sizing.lots:,}")
        table.add_row("Capital", f"{capital:,.0f}")
        risk_amt = getattr(chosen_sizing, "risk_amount", None)
        if risk_amt is not None:
            try:
                table.add_row("Risk amount", f"{float(risk_amt):,.0f}")
            except (TypeError, ValueError):
                pass
    else:
        table.add_row(
            "Sizing",
            "add --capital for lots / stop / target (structure)",
        )

    table.add_row("Guidance", Text(plan_text, style=f"bold {plan_style}"))
    table.add_row("Judgment desk", f"saham screen accum {ticker}")
    return panel(table, title="Structure")


def _build_data_panel(
    data_freshness,
    broker_detail,
    broker_quality_note,
    accum,
    auto_refresh: bool = False,
    refresh_actions: tuple = (),
) -> Any:
    warnings = list(getattr(data_freshness, "warnings", ()) or ())
    candle_lag = next((w for w in warnings if "candle" in w.lower()), "")
    broker_lag = next((w for w in warnings if "broker" in w.lower()), "")

    table = compact_table(show_header=False)
    table.add_column("Source", style="bold")
    table.add_column("Value")
    table.add_column("Detail")

    table.add_row("Candles", fmt_date(data_freshness.candle_end), candle_lag or "ok")
    table.add_row("Broker", fmt_date(data_freshness.broker_end), broker_lag or "ok")

    if broker_quality_note is not None:
        note_style = "yellow" if broker_quality_note.level == "warning" else "cyan"
        table.add_row(
            "Quality",
            Text(broker_quality_note.level.upper(), style=note_style),
            broker_quality_note.message,
        )
    elif broker_detail is None:
        table.add_row("Quality", "N/A", "broker detail unavailable")

    missing = getattr(data_freshness, "missing", []) or []
    if missing:
        table.add_row(
            "Missing",
            ", ".join(missing),
            "add --with-fundamental or fetch data",
        )

    if accum is not None and getattr(accum, "ticker_notation", None):
        notation = accum.ticker_notation
        table.add_row(
            "Notation",
            getattr(notation, "listing_board", "") or "-",
            (
                f"haircut={getattr(notation, 'haircut_percentage', '')}"
                if getattr(notation, "haircut_percentage", None)
                else notation_detail(notation)
            ),
        )

    return panel(table, title="Data")
