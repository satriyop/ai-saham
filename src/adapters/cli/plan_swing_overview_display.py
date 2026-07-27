"""
Verdict-first overview panel construction for saham analyze swing.

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
    from src.application.dto.swing_analysis import SignalAssessmentAvailability
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
    _build_market_context_panel,
    _build_plan_panel,
    _build_risk_panel,
    _build_signal_panel,
    _market_label,
    _risk_label,
    _signal_label,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.dto.swing_analysis import SignalAssessmentAvailability
from src.application.dto.swing_broker_detail import (
    BrokerDetail,
    BrokerQualityNote,
)
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


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


def _modules_text(
    setup_eval: Any | None,
    capital: int | None,
    include_strategy: bool,
    include_sentiment: bool,
    include_flow_detail: bool,
    include_signal_detail: bool,
    include_risk_detail: bool,
    include_market_detail: bool,
    market_regime: MarketContext | None,
) -> str:
    modules = [
        f"Market Context {'on' if market_regime is not None else 'off'}",
        f"setup {'on' if setup_eval is not None else 'off'}",
        f"sizing {'on' if capital is not None else 'off'}",
        f"strategy {'on' if include_strategy else 'off'}",
        f"sentiment {'on' if include_sentiment else 'off'}",
        f"flow-detail {'on' if include_flow_detail else 'off'}",
    ]
    detail_bits = []
    if include_signal_detail:
        detail_bits.append("signal")
    if include_risk_detail:
        detail_bits.append("risk")
    if include_market_detail:
        detail_bits.append("market")
    modules.append(f"detail {','.join(detail_bits) if detail_bits else 'off'}")
    return " | ".join(modules)


def _top_findings(
    setup_eval: Any | None,
    risk_resp: Any | None,
    broker_quality_note: BrokerQualityNote | None,
    data_freshness: Any,
    trade_setup: Any | None,
) -> list[Text]:
    findings: list[Text] = []
    if trade_setup is not None and trade_setup.action.value.startswith("BLOCKED"):
        findings.append(Text(f"- Action blocked: {trade_setup.rationale}", style="red"))
    if setup_eval is not None and setup_eval.failed_reasons:
        for reason in setup_eval.failed_reasons[:2]:
            findings.append(Text(f"- Setup gate: {reason}", style="yellow"))
    if risk_resp is not None and risk_resp.assessment.gate_triggered:
        findings.append(Text(f"- Risk gate: {risk_resp.assessment.gate_triggered}", style="red"))
    if broker_quality_note is not None:
        style = "yellow" if broker_quality_note.level == "warning" else "cyan"
        findings.append(Text(f"- Broker: {broker_quality_note.message}", style=style))
    for warning in data_freshness.warnings[:2]:
        findings.append(Text(f"- Data: {warning}", style="yellow"))
    if not findings:
        findings.append(Text("- No blocking issues surfaced in displayed checks.", style="green"))
    return findings[:5]


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
    strategy_name: str,
    data_freshness: SwingDataFreshness,
    broker_detail: BrokerDetail | None,
    accum: AccumulationCandidate | None,
    risk_resp,
    atr_value: Decimal | None,
    sizing: SizingResult | None,
    setup_eval: Any | None,
    setup_sizing: Any | None,
    broker_quality_note: BrokerQualityNote | None,
    market_regime: MarketContext | None,
    capital: int | None,
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    config: SwingDisplayConfig,
    signal_assessment_availability: SignalAssessmentAvailability,
    include_strategy: bool = False,
    include_sentiment: bool = False,
    include_flow_detail: bool = False,
    include_signal_detail: bool = False,
    include_risk_detail: bool = False,
    include_market_detail: bool = False,
    signal_assessment=None,
    trade_setup=None,
    market_context_signal_preview=None,
    market_context_risk_preview=None,
    market_context_trade_setup_preview=None,
    with_technical_gate: bool = False,
    sector_context_evidence: "SectorContextEvidence | None" = None,
    effective_session=None,
) -> None:
    if not isinstance(signal_assessment_availability, SignalAssessmentAvailability):
        raise TypeError("signal_assessment_availability must be a SignalAssessmentAvailability")

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

    signal_value, signal_style, _ = _signal_label(signal_source, signal_assessment_availability)
    risk_value, risk_style, _ = _risk_label(risk_resp)
    market_value, market_style, _ = _market_label(market_regime)

    # Verdict table (no Accum column)
    verdict = compact_table()
    verdict.add_column("Action")
    verdict.add_column("Price", justify="right")
    verdict.add_column("Signal")
    verdict.add_column("Risk")
    verdict.add_column("Market")
    verdict.add_column("Setup")
    verdict.add_row(
        Text(action_value, style=action_style),
        price,
        Text(signal_value, style=signal_style),
        Text(risk_value, style=risk_style),
        Text(market_value, style=market_style),
        Text(setup_value, style=setup_style),
    )

    chosen_sizing = setup_sizing or sizing

    sections = [
        panel(verdict, title="Verdict"),
        _build_signal_panel(signal_source, signal_assessment_availability),
        _build_risk_panel(risk_resp, with_technical_gate),
    ]
    if market_regime is not None:
        sections.append(
            _build_market_context_panel(
                market_regime,
                market_context_signal_preview,
                market_context_risk_preview,
                canonical_signal=signal_source,
            )
        )
    sections += [
        _build_plan_panel(plan_text, plan_style, capital, chosen_sizing),
        _build_data_panel(data_freshness, broker_detail, broker_quality_note, accum),
    ]

    if effective_session is not None:
        subtitle = f"{today.isoformat()} · {format_effective_session_label(effective_session)}"
    else:
        subtitle = today.isoformat()

    console().print(
        panel(
            Group(*sections),
            title=f"Swing Analysis - {ticker}",
            subtitle=subtitle,
        )
    )
