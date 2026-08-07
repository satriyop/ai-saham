"""
Structure-first overview for saham plan swing (ADR-054 S4).

Layer: Adapter

This module renders facts already produced by application/domain. It must
not compute business action, and must not introduce or alter thresholds.
It may use SwingDisplayConfig only for presentation labels.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.application.dto.accumulation_screen import AccumulationCandidate
    from src.application.dto.plan_swing import ScreenJudgmentReference
    from src.application.services.position_sizer import SizingResult
    from src.application.services.swing_data_freshness import SwingDataFreshness

from rich.console import Group
from rich.text import Text

from src.adapters.cli.effective_session_display import format_effective_session_label
from src.adapters.cli.plan_swing_formatters import (
    SwingDisplayConfig,
    fmt_pct,
    signal_label,
)
from src.adapters.cli.plan_swing_overview_panels import (
    _build_data_panel,
    _build_signal_panel,
    _build_structure_panel,
    _signal_label,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.dto.plan_swing import ScreenJudgmentReference
from src.application.dto.swing_broker_detail import (
    BrokerDetail,
    BrokerQualityNote,
)


def _trade_action_label(trade_setup: Any | None) -> tuple[str, str, str]:
    if trade_setup is None:
        return "N/A", "white", "TradeSetup unavailable"
    style = {
        "ENTER": "bold green",
        "WATCH": "yellow",
        "AVOID": "red",
        "BLOCKED_EXECUTION": "bold red",
        "BLOCKED_STRUCTURAL": "bold red",
    }.get(trade_setup.action.value, "white")
    return trade_setup.action.short, style, trade_setup.rationale


_SETUP_ENTRY_AUTHORITY_REASON_MARKERS = (
    "no standalone entry authority",
    "requires phase",
    "requires setup phase for ENTER",
)


def _setup_entry_authority_block_reason(signal_assessment: Any | None) -> str | None:
    """Return the DecisionPolicy constraint reason that blocked ENTER on entry
    authority/phase grounds, if any fired — so display text does not contradict
    the actual TradeSetup.action with a stale "matched" framing."""
    assessment = getattr(signal_assessment, "assessment", None)
    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    reasons = getattr(constraints, "constraint_reasons", ()) if constraints else ()
    for reason in reasons:
        if any(marker in reason for marker in _SETUP_ENTRY_AUTHORITY_REASON_MARKERS):
            return reason
    return None


def _setup_match_label(setup_eval: Any | None) -> tuple[str, str]:
    if setup_eval is None:
        return "not applied", "bright_black"
    style = {
        "MATCH": "bold green",
        "PARTIAL": "yellow",
        "NO_MATCH": "red",
    }.get(setup_eval.match.value, "white")
    return setup_eval.match.value, style


def _accumulation_label(accum: Any | None, config: SwingDisplayConfig) -> tuple[str, str, str]:
    if accum is None:
        return "missing", "red", "no accumulation candidate"
    label = signal_label(accum, config)
    style = (
        "bold green"
        if accum.accum_score >= config.enter_min_score
        else ("yellow" if accum.accum_score >= config.watch_min_score else "red")
    )
    detail = (
        f"foreign-flow score {accum.accum_score:.1f}; streak {accum.consecutive_streak}s; "
        f"net {accum.net_buy_days}/{accum.total_days}; flow {fmt_pct(accum.avg_flow_ratio, True)}"
    )
    return label.upper(), style, detail


def flow_trigger_blocked_text(reason: str) -> str | None:
    messages = {
        "flow_trigger_blocked:no_setup_phase": ("Flow trigger blocked: setup phase unavailable"),
        "flow_trigger_blocked:setup_phase_not_breakout_confirmation": (
            "Flow trigger blocked: setup phase is not BREAKOUT_CONFIRMATION"
        ),
        "flow_trigger_blocked:no_flow_confirmation_evidence": (
            "Flow trigger blocked: flow evidence unavailable"
        ),
        "flow_trigger_blocked:flow_not_confirmed": (
            "Flow trigger blocked: flow confirmation is not CONFIRMED"
        ),
    }
    return messages.get(reason)


def _broker_label(
    broker_detail: BrokerDetail | None,
    broker_quality_note: BrokerQualityNote | None,
) -> tuple[str, str, str]:
    if broker_quality_note is not None:
        style = "yellow" if broker_quality_note.level == "warning" else "cyan"
        return broker_quality_note.level.upper(), style, broker_quality_note.message
    if broker_detail is None:
        return "N/A", "white", "broker detail unavailable"
    return broker_detail.quality, "cyan", broker_detail.broker_weight_quality


def _price_text(accum: Any | None, sizing: Any | None, setup_sizing: Any | None) -> str:
    if accum is not None:
        return f"{float(accum.current_price):,.0f}"
    chosen = setup_sizing or sizing
    if chosen is not None:
        return f"{float(chosen.entry_price):,.0f}"
    return "N/A"


def _refresh_text(data_freshness: Any) -> str:
    actions = getattr(data_freshness, "refresh_actions", ()) or ()
    if not actions:
        return "not reported"
    return ", ".join(str(action) for action in actions)


def _gate_meaning(label: str) -> str:
    meanings = {
        "score": "composite foreign-flow strength",
        "fvwap%": "foreign holders still have price support incentive",
        "trend": "chart regime required by the setup",
        "flow_pct": "foreign net flow is meaningful versus turnover",
        "RSI present": "momentum indicator is available",
        "RSI": "momentum is not overextended",
        "RSI lower": "pullback has enough momentum",
        "RSI upper": "pullback is not overbought",
        "bb_width_pctile": "volatility is compressed",
        "smart_flow": "smart-money flow is net supportive",
        "smart_share_pct": "smart-money share is large enough",
        "noise_share_pct": "noise-flow dominance is controlled",
        "smart_net_selling": "smart-money is not distributing",
        "broker detail": "named-broker attribution is available",
        "setup enabled": "setup is enabled in config",
        "broker flow data": "foreign-flow score exists",
    }
    return meanings.get(label, "setup-specific requirement")


def format_failed_gates_summary(setup_eval: Any) -> str:
    return "Failed gates: " + "; ".join(setup_eval.failed_reasons)


def setup_gates_group(
    setup_eval: Any,
    broker_quality_note: BrokerQualityNote | None,
) -> Group:
    gates_group = []
    match_style = {
        "MATCH": "bold green",
        "PARTIAL": "yellow",
        "NO_MATCH": "red",
    }.get(setup_eval.match.value, "white")
    gates_group.append(
        Text(
            f"{setup_eval.match.value} - {setup_eval.name}",
            style=match_style,
        )
    )

    gates_table = compact_table()
    gates_table.add_column("Result", style="bold")
    gates_table.add_column("Gate")
    gates_table.add_column("Actual")
    gates_table.add_column("Required")
    gates_table.add_column("Meaning")

    ordered_gates = sorted(setup_eval.gates, key=lambda gate: gate.passed)
    for gate in ordered_gates:
        status_text = Text(
            "PASS" if gate.passed else "FAIL",
            style="green" if gate.passed else "red",
        )
        gates_table.add_row(
            status_text,
            gate.label,
            str(gate.actual),
            str(gate.required),
            _gate_meaning(gate.label),
        )
    gates_group.append(gates_table)

    if setup_eval.failed_reasons:
        gates_group.append(Text(format_failed_gates_summary(setup_eval), style="yellow"))
    else:
        gates_group.append(Text("All setup gates passed.", style="green"))

    if broker_quality_note is not None:
        note_style = "yellow" if broker_quality_note.level == "warning" else "cyan"
        gates_group.append(Text(f"Broker note: {broker_quality_note.message}", style=note_style))

    return Group(*gates_group)


def swing_plan_text(
    ticker: str,
    capital: int | None,
    atr_value: Decimal | None,
    sizing: Any | None,
    setup_eval: Any | None,
    setup_sizing: Any | None,
    config: SwingDisplayConfig,
    trade_setup: Any | None = None,
    signal_assessment: Any | None = None,
) -> tuple[str, str]:
    if setup_eval is not None:
        if setup_eval.passed:
            block_reason = _setup_entry_authority_block_reason(signal_assessment)
            if block_reason is not None:
                action_label = getattr(getattr(trade_setup, "action", None), "value", "WATCH")
                return (
                    f"Setup matched as confirmation evidence, but action is "
                    f"{action_label}: {block_reason}",
                    "yellow",
                )
        if setup_eval.passed and setup_sizing and setup_sizing.lots > 0:
            return (
                f"Setup matched. Consider {setup_sizing.lots} lots at "
                f"{float(setup_sizing.entry_price):,.0f}; TP "
                f"{float(setup_sizing.target_price):,.0f}; SL "
                f"{float(setup_sizing.stop_price):,.0f}; max hold "
                f"{config.foreign_bounce_max_hold_days} trading days.",
                "green",
            )
        if setup_eval.passed:
            return ("Setup matched. Add --capital to compute lot size.", "green")
        if setup_eval.match.value == "PARTIAL":
            return (
                "Setup is partial. Wait for failed gates to improve before treating it as a match.",
                "yellow",
            )
        return ("Setup does not match. Gates are not aligned.", "red")
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
            f"Fetch more data to enable position sizing "
            f"(run saham fetch market {ticker} --days 90).",
            "yellow",
        )
    return (
        "No setup or sizing plan requested. Use --setup for setup gates or --capital for sizing.",
        "bright_black",
    )


def print_swing_rich_overview(
    ticker: str,
    today: date,
    data_freshness: SwingDataFreshness,
    broker_detail: BrokerDetail | None,
    accum: AccumulationCandidate | None,
    atr_value: Decimal | None,
    sizing: SizingResult | None,
    setup_eval: Any | None,
    setup_sizing: Any | None,
    broker_quality_note: BrokerQualityNote | None,
    capital: int | None,
    config: SwingDisplayConfig,
    screen_judgment: ScreenJudgmentReference,
    include_signal_detail: bool = False,
    signal_assessment=None,
    trade_setup=None,
    effective_session=None,
) -> None:
    if not isinstance(screen_judgment, ScreenJudgmentReference):
        raise TypeError("screen_judgment must be a ScreenJudgmentReference")

    signal_source = signal_assessment or getattr(accum, "signal_assessment", None)

    plan_text, plan_style = swing_plan_text(
        ticker,
        capital,
        atr_value,
        sizing,
        setup_eval,
        setup_sizing,
        config,
        trade_setup=trade_setup,
        signal_assessment=signal_source,
    )

    action_value, action_style, action_detail = _trade_action_label(trade_setup)
    setup_value, setup_style = _setup_match_label(setup_eval)
    price = _price_text(accum, sizing, setup_sizing)

    signal_value, signal_style, _ = _signal_label(signal_source, screen_judgment)
    chosen_sizing = setup_sizing or sizing

    # The only judgment context shown here is the referenced screen output.
    context = compact_table()
    context.add_column("Signal")
    context.add_column("Setup")
    context.add_row(
        Text(signal_value, style=signal_style),
        Text(setup_value, style=setup_style),
    )

    sections = [
        _build_structure_panel(
            action_value=action_value,
            action_style=action_style,
            action_detail=action_detail,
            price=price,
            plan_text=plan_text,
            plan_style=plan_style,
            capital=capital,
            chosen_sizing=chosen_sizing,
            setup_value=setup_value,
            setup_style=setup_style,
            ticker=ticker,
        ),
        panel(
            Group(
                context,
                Text(
                    "\nContext only — deep judgment: "
                    f"saham screen accum {ticker}. "
                    "Signal detail: --full.",
                    style="dim",
                ),
            ),
            title="Context (judgment)",
        ),
    ]
    # Signal detail is a view of the exact embedded screen result.
    if include_signal_detail:
        sections.append(_build_signal_panel(signal_source, screen_judgment))
    sections.append(
        _build_data_panel(data_freshness, broker_detail, broker_quality_note, accum),
    )

    if effective_session is not None:
        subtitle = f"{today.isoformat()} · {format_effective_session_label(effective_session)}"
    else:
        subtitle = today.isoformat()

    console().print(
        panel(
            Group(*sections),
            title=f"Swing Structure - {ticker}",
            subtitle=subtitle,
        )
    )
