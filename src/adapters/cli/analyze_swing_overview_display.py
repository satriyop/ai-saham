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
from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
)
from src.adapters.cli.analyze_swing_formatters import (
    SwingDisplayConfig,
    fmt_date,
    fmt_pct,
    notation_detail,
    signal_label,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
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


def _signal_label(signal_assessment: Any | None) -> tuple[str, str, str]:
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


def _accumulation_label(accum: Any | None, config: SwingDisplayConfig) -> tuple[str, str, str]:
    if accum is None:
        return "missing", "red", "no accumulation candidate"
    label = signal_label(accum, config)
    style = "bold green" if accum.foreign_flow_score >= config.enter_min_score else (
        "yellow" if accum.foreign_flow_score >= config.watch_min_score else "red"
    )
    detail = (
        f"foreign-flow score {accum.foreign_flow_score:.1f}; streak {accum.consecutive_streak}s; "
        f"net {accum.net_buy_days}/{accum.total_days}; flow {fmt_pct(accum.avg_flow_ratio, True)}"
    )
    return label.upper(), style, detail


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


def flow_trigger_blocked_text(reason: str) -> str | None:
    messages = {
        "flow_trigger_blocked:no_setup_phase": (
            "Flow trigger blocked: setup phase unavailable"
        ),
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
        findings.append(
            Text(f"- Risk gate: {risk_resp.assessment.gate_triggered}", style="red")
        )
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
            f"Fetch more data to enable position sizing (run saham fetch market {ticker} --days 90).",
            "yellow",
        )
    return (
        "No setup or sizing plan requested. Use --setup for setup gates or --capital for sizing.",
        "bright_black",
    )


def _build_signal_panel(signal_assessment) -> Any:
    if signal_assessment is None:
        return panel(Text("Signal unavailable", style="dim"), title="Signal")

    assessment = signal_assessment.assessment
    strength_value, strength_style, _ = _signal_label(signal_assessment)
    coverage_score = (
        getattr(assessment, "coverage_score", None)
        or getattr(signal_assessment, "evidence_confidence", None)
        or 1.0
    )

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
            ("evidence_confidence", "Cov%", True),
        ]
        factor_table = compact_table()
        for _, header, _ in key_map:
            factor_table.add_column(header, justify="right")
        factor_table.add_column("Flags")
        factor_table.add_row(
            *(
                (f"{breakdown[key]:.0f}%" if is_pct else str(round(breakdown[key])))
                if key in breakdown else "-"
                for key, _, is_pct in key_map
            ),
            " ".join(_flag_abbr.get(f, f[:3]) for f in active_flags) or "-",
        )
        items.append(factor_table)

    constraints = getattr(assessment, "decision_constraints", None)
    if constraints is not None:
        reasons = list(getattr(constraints, "constraint_reasons", ()) or ())
        detail = (
            f"max {constraints.max_decision}; "
            f"size x{constraints.effective_size_multiplier:.2f}"
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
                f"{assessment.score:.0f} ({assessment.entry_quality.value}) · "
                + ", ".join(markers)
            )
    table.add_row("Signal", signal_summary, signal_detail)

    if market_regime.gate_tightening:
        table.add_row("Gates", "tightened", "see --with-market-detail")
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
            f"haircut={getattr(notation, 'haircut_percentage', '')}"
            if getattr(notation, "haircut_percentage", None)
            else notation_detail(notation),
        )

    return panel(table, title="Data")


def print_swing_rich_overview(
    ticker: str,
    today: date,
    strategy_name: str,
    data_freshness: DataFreshness,
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
) -> None:
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

    signal_value, signal_style, _ = _signal_label(signal_source)
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
        _build_signal_panel(signal_source),
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

    console().print(
        panel(
            Group(*sections),
            title=f"Swing Analysis - {ticker}",
            subtitle=today.isoformat(),
        )
    )
