"""
Panel builders for the saham analyze swing verdict-first overview.

Owns per-section Rich panel construction (Signal, Risk, Market Context,
Plan, Data) and the label/style/detail helpers that feed them.
print_swing_rich_overview() in plan_swing_overview_display.py owns the
Verdict table, overall panel assembly, and printing; it calls into this
module for each section panel.

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
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
)
from src.application.dto.swing_analysis import (
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
)
from src.domain.value_objects.market_context import MarketContext


def _signal_label(
    signal_assessment: Any | None,
    availability: SignalAssessmentAvailability,
) -> tuple[str, str, str]:
    if not isinstance(availability, SignalAssessmentAvailability):
        raise TypeError("availability must be a SignalAssessmentAvailability")

    if availability.status is SignalAssessmentStatus.UNAVAILABLE:
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


def _risk_label(risk_resp: Any | None) -> tuple[str, str, str]:
    if risk_resp is None:
        return "N/A", "white", "risk unavailable"
    assessment = risk_resp.assessment
    gate = assessment.gate_triggered
    if gate:
        return "BLOCKED", "bold red", f"gate {gate} (conf {assessment.gate_confidence or 0}/100)"
    return "OPEN", "bold green", "no gate fired"


def _technical_label(risk_resp: Any | None, with_technical_gate: bool) -> tuple[str, str, str]:
    """Engine-summary row for the optional TechnicalGate."""
    if not with_technical_gate:
        return "off", "bright_black", "use --with-technical-gate to enable"
    if risk_resp is None:
        return "on", "white", "gate: unavailable"
    snap = risk_resp.assessment.indicators
    sma_pos = "above" if snap.sma > snap.ema else ("below" if snap.sma < snap.ema else "==")
    summary = f"RSI {float(snap.rsi):.0f} · SMA {sma_pos}"
    gate = risk_resp.assessment.gate_triggered
    if gate == "TechnicalGate":
        return summary, "bold red", "gate: BLOCKED"
    return summary, "cyan", "gate: open"


def _market_label(market_regime: MarketContext | None) -> tuple[str, str, str]:
    if market_regime is None:
        return "off", "bright_black", "run with --with-market-context for regime preview"
    label = REGIME_DISPLAY_LABEL.get(market_regime.regime.value, market_regime.regime.value)
    score = context_conviction_score(market_regime)
    style = {
        "RISK_ON": "bold green",
        "NEUTRAL": "yellow",
        "RISK_OFF": "bold red",
        "VOLATILE": "bold red",
    }.get(market_regime.regime.value, "white")
    return label, style, f"conviction {score}/7"


def _build_signal_panel(
    signal_assessment: Any | None,
    availability: SignalAssessmentAvailability,
) -> Any:
    if not isinstance(availability, SignalAssessmentAvailability):
        raise TypeError("availability must be a SignalAssessmentAvailability")

    if availability.status is SignalAssessmentStatus.UNAVAILABLE:
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


def _build_risk_panel(risk_resp, with_technical_gate) -> Any:
    gate_table = compact_table(show_header=False)
    gate_table.add_column("Gate", style="bold")
    gate_table.add_column("Summary")
    gate_table.add_column("Detail")

    risk_value, risk_style, risk_detail = _risk_label(risk_resp)
    gate_table.add_row("Gates", Text(risk_value, style=risk_style), risk_detail)

    tech_value, tech_style, tech_detail = _technical_label(risk_resp, with_technical_gate)
    gate_table.add_row("Technical", Text(tech_value, style=tech_style), tech_detail)

    items: list = [gate_table]
    if risk_resp is not None and risk_resp.assessment.gate_triggered:
        items.append(Text(""))
        items.append(Text("Why", style="bold cyan"))
        for line in risk_resp.assessment.rationale_list[:3]:
            items.append(Text(f"  {line}", style="dim"))

    renderable = Group(*items) if len(items) > 1 else items[0]
    return panel(renderable, title="Risk")


def _build_market_context_panel(
    market_regime,
    mc_signal_preview,
    mc_risk_preview,
    canonical_signal=None,
) -> Any:
    table = compact_table(show_header=False)
    table.add_column("Dim", style="bold")
    table.add_column("Summary")
    table.add_column("Detail")

    market_value, market_style, market_detail = _market_label(market_regime)
    table.add_row("Regime", Text(market_value, style=market_style), market_detail)

    signal_summary = "no impact"
    signal_detail = ""
    signal_for_context = mc_signal_preview or canonical_signal
    if signal_for_context is not None:
        assessment = signal_for_context.assessment
        bd_dict = dict(assessment.breakdown)
        regime_conditioned = bool(bd_dict.get("regime_conditioning"))
        gate_tightened = bool(bd_dict.get("gate_tightening"))
        if regime_conditioned or gate_tightened:
            signal_summary = "conditioned"
            markers = []
            if regime_conditioned:
                markers.append("regime")
            if gate_tightened:
                markers.append("gate tightening")
            signal_detail = (
                f"{assessment.score:.0f} ({assessment.entry_quality.value}) · " + ", ".join(markers)
            )
    table.add_row("Signal", signal_summary, signal_detail)

    if market_regime.gate_tightening:
        table.add_row("Gates", "tightened", "see Market Context detail")
    else:
        table.add_row("Gates", "open", "gates unchanged")

    return panel(table, title="Market Context")


def _build_plan_panel(plan_text, plan_style, capital, chosen_sizing) -> Any:
    if not capital or chosen_sizing is None:
        return panel(Text(plan_text, style=f"bold {plan_style}"), title="Plan")

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
    return panel(table, title="Plan")


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
