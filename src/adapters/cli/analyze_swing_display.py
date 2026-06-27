"""
Display helpers for saham analyze swing commands.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    fmt_money_short,
    fmt_money_short_signed,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
    context_factor_value,
    context_warnings,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse
from src.domain.value_objects.market_context import MarketContext


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


def format_failed_gates_summary(setup_eval: Any) -> str:
    return "Failed gates: " + "; ".join(setup_eval.failed_reasons)


def swing_summary_parts(
    accum: Any | None,
    risk_resp: Any,
    backtest_result: Any,
    sentiment_resp: Any,
) -> list[str]:
    parts = []
    if accum:
        parts.append(f"Score {accum.score:.1f}")
    if risk_resp and risk_resp.assessment.gate_triggered:
        parts.append(f"gate: BLOCKED ({risk_resp.assessment.gate_triggered})")
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
    setup_eval: Any | None,
    setup_sizing: Any | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
    config: SwingDisplayConfig,
) -> tuple[str, str]:
    strategy_override = (
        strategy_risk_level == "HIGH_RISK"
        and setup_eval is not None
        and setup_eval.passed
    )

    if setup_eval is not None:
        if strategy_override:
            return (
                f"AVOID (strategy gate: '{strategy_risk_name}' signals HIGH_RISK; setup matched but technical signal says exit).",
                "red",
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
    style = "bold green" if accum.score >= config.enter_min_score else (
        "yellow" if accum.score >= config.watch_min_score else "red"
    )
    detail = (
        f"score {accum.score:.1f}; streak {accum.consecutive_streak}s; "
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
        "score": "overall accumulation conviction",
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
        "broker flow data": "accumulation evidence exists",
    }
    return meanings.get(label, "setup-specific requirement")


def _setup_gates_group(
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


def _build_signal_panel(signal_assessment) -> Any:
    if signal_assessment is None:
        return panel(Text("Signal unavailable", style="dim"), title="Signal")

    assessment = signal_assessment.assessment
    strength_value, strength_style, _ = _signal_label(signal_assessment)

    headline_table = compact_table(show_header=False)
    headline_table.add_column("Strength")
    headline_table.add_column("Score")
    headline_table.add_column("Spacer")
    headline_table.add_row(
        Text(strength_value, style=strength_style),
        f"score {assessment.score:.1f}  {assessment.entry_quality.value}",
        "",
    )

    items = [headline_table]

    breakdown = getattr(assessment, "breakdown_dict", None) or {}
    if breakdown:
        key_map = [
            ("bandar_intensity", "Bandar"),
            ("foreign_flow_quality", "Foreign"),
            ("insider_activity", "Insider"),
            ("seasonality_edge", "Season"),
            ("analyst_consensus", "Analyst"),
            ("forward_valuation", "Fwd"),
        ]
        factor_table = compact_table()
        for _, header in key_map:
            factor_table.add_column(header, justify="right")
        factor_table.add_row(
            *[str(round(breakdown.get(key, 0))) for key, _ in key_map]
        )
        items.append(factor_table)

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
    if mc_signal_preview is not None and canonical_signal is not None:
        before = canonical_signal.assessment
        after = mc_signal_preview.assessment
        mult = getattr(after, "market_multiplier", None)
        if mult is None:
            mult = (after.score / before.score) if before.score else 1.0
        if before.score != after.score or before.entry_quality.value != after.entry_quality.value:
            signal_summary = f"x{mult:.2f}"
            signal_detail = (
                f"{before.score:.0f}->{after.score:.0f} "
                f"({before.entry_quality.value}->{after.entry_quality.value})"
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
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
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
) -> None:
    plan_text, plan_style = swing_plan_text(
        ticker,
        capital,
        atr_value,
        sizing,
        setup_eval,
        setup_sizing,
        strategy_risk_level,
        strategy_risk_name,
        config,
    )

    action_value, action_style, action_detail = _trade_action_label(trade_setup)
    setup_value, setup_style = _setup_match_label(setup_eval)
    price = _price_text(accum, sizing, setup_sizing)

    signal_source = signal_assessment or getattr(accum, "signal_assessment", None)
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





def _market_context_preview_group(
    market_regime: Any,
    canonical_signal: Any | None,
    preview_signal: Any | None,
    canonical_risk: Any | None,
    preview_risk: Any | None,
    canonical_trade_setup: Any | None,
    preview_trade_setup: Any,
) -> Group:
    items: list = []

    regime_label = REGIME_DISPLAY_LABEL.get(market_regime.regime.value, market_regime.regime.value)
    items.append(Text(f"Regime: {regime_label}", style="bold cyan"))

    if canonical_signal is not None and preview_signal is not None:
        raw_score = canonical_signal.assessment.score
        preview_score = preview_signal.assessment.score
        raw_eq = canonical_signal.assessment.entry_quality.value
        preview_eq = preview_signal.assessment.entry_quality.value
        if raw_score != preview_score or raw_eq != preview_eq:
            impact = f"Signal {raw_score:.0f} → {preview_score:.0f}; {raw_eq} would become {preview_eq}"
        else:
            impact = "No signal score change (multiplier=1.0)"
        items.append(Text(f"Signal impact:  {impact}", style="yellow" if raw_eq != preview_eq else "dim"))

    if canonical_risk is not None and preview_risk is not None:
        raw_gate = canonical_risk.assessment.gate_triggered
        preview_gate = preview_risk.assessment.gate_triggered
        if preview_gate and not raw_gate:
            items.append(Text(f"Risk impact:    regime gate would trigger ({preview_gate})", style="yellow"))
        elif preview_gate and raw_gate and preview_gate != raw_gate:
            items.append(Text(f"Risk impact:    gate upgraded {raw_gate} → {preview_gate}", style="yellow"))
        else:
            items.append(Text("Risk impact:    no additional gate triggered", style="dim"))

    canonical_action = canonical_trade_setup.action.value if canonical_trade_setup else "N/A"
    preview_action = preview_trade_setup.action.value
    if canonical_action != preview_action:
        items.append(Text(
            f"Preview:        TradeSetup would change {canonical_action} → {preview_action}",
            style="bold yellow",
        ))
    else:
        items.append(Text("Preview:        No action change in preview.", style="dim green"))
    items.append(Text(f"Final (unchanged): {canonical_action}", style="bold"))

    return Group(*items)


def print_swing_output(
    ticker: str,
    today: date,
    strategy_name: str,
    data_freshness: DataFreshness,
    flow_detail: FlowDetail | None,
    broker_detail: BrokerDetail | None,
    window: int,
    accum: "AccumulationCandidate | None",
    risk_resp,
    atr_value: "Decimal | None",
    sizing: "SizingResult | None",
    setup_eval: "Any | None",
    setup_sizing: "Any | None",
    broker_quality_note: BrokerQualityNote | None,
    market_regime: "MarketContext | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    sentiment_verbose: bool,
    include_strategy: bool,
    include_sentiment: bool,
    include_flow_detail: bool,
    include_signal_detail: bool,
    include_risk_detail: bool,
    include_market_detail: bool,
    strategy_risk_level: str | None = None,
    strategy_risk_name: str | None = None,
    signal_assessment=None,
    trade_setup=None,
    market_context_signal_preview=None,
    market_context_risk_preview=None,
    market_context_trade_setup_preview=None,
    config: SwingDisplayConfig | None = None,
    with_technical_gate: bool = False,
) -> None:
    config = config or SwingDisplayConfig(
        enter_min_score=70,
        watch_min_score=50,
        coiled_spring_bb_pctile=0.2,
        coiled_spring_min_score=70,
        strong_min_score=80,
        strong_min_streak=3,
        building_min_score=60,
        building_min_streak=2,
        foreign_bounce_max_hold_days=10,
    )
    # Print the primary Decision Dashboard Panel (Panel 1)
    print_swing_rich_overview(
        ticker=ticker,
        today=today,
        strategy_name=strategy_name,
        data_freshness=data_freshness,
        broker_detail=broker_detail,
        accum=accum,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        setup_eval=setup_eval,
        setup_sizing=setup_sizing,
        broker_quality_note=broker_quality_note,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=sentiment_warning,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        config=config,
        include_strategy=include_strategy,
        include_sentiment=include_sentiment,
        include_flow_detail=include_flow_detail,
        include_signal_detail=include_signal_detail,
        include_risk_detail=include_risk_detail,
        include_market_detail=include_market_detail,
        signal_assessment=signal_assessment,
        trade_setup=trade_setup,
        market_context_signal_preview=market_context_signal_preview,
        market_context_risk_preview=market_context_risk_preview,
        market_context_trade_setup_preview=market_context_trade_setup_preview,
        with_technical_gate=with_technical_gate,
    )

    # ── Market Context Preview Panel ─────────────────────────────────────────
    if market_context_trade_setup_preview is not None and market_regime is not None:
        _preview_group = _market_context_preview_group(
            market_regime=market_regime,
            canonical_signal=signal_assessment,
            preview_signal=market_context_signal_preview,
            canonical_risk=risk_resp,
            preview_risk=market_context_risk_preview,
            canonical_trade_setup=trade_setup,
            preview_trade_setup=market_context_trade_setup_preview,
        )
        console().print("")
        console().print(
            panel(
                _preview_group,
                title="MARKET CONTEXT PREVIEW",
                subtitle="evidence only — does not change final TradeSetup",
            )
        )

    # ── Panel 2: SETUP EVIDENCE ─────────────────────────────────────────────
    if setup_eval is not None:
        console().print("")
        console().print(
            panel(
                _setup_gates_group(setup_eval, broker_quality_note),
                title="SETUP EVIDENCE",
            )
        )

    # ── Panel 3: ENGINE DETAIL PANELS ───────────────────────────────────────
    regime_text = []
    if include_market_detail and market_regime is not None:
        _rlabel = REGIME_DISPLAY_LABEL.get(market_regime.regime.value, market_regime.regime.value)
        _rscore = context_conviction_score(market_regime)
        regime_text.append(Text(f"Market Regime: {_rlabel} ({_rscore}/7)", style="bold cyan"))
        regime_table = compact_table()
        regime_table.add_column("Breadth SMA20")
        regime_table.add_column("Conviction")
        regime_table.add_column("Regime")
        breadth = context_factor_value(market_regime, "idx_breadth")
        regime_table.add_row(
            fmt_pct(breadth),
            f"{market_regime.conviction:.2f}",
            market_regime.regime.value,
        )
        regime_text.append(regime_table)

    risk_text = []
    if include_risk_detail and risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        if r.gate_triggered:
            _verdict = f"BLOCKED — gate {r.gate_triggered} (conf {r.gate_confidence or 0}/100)"
        else:
            _verdict = "OPEN — no gate fired"
        risk_text.append(Text(f"Risk Verdict: {_verdict}", style="bold cyan"))
        risk_table = compact_table()
        risk_table.add_column("SMA20")
        risk_table.add_column("EMA20")
        risk_table.add_column("RSI14")
        risk_table.add_row(
            f"{float(snap.sma):,.0f}",
            f"{float(snap.ema):,.0f}",
            f"{float(snap.rsi):.1f}"
        )
        risk_text.append(risk_table)
        for reason in r.rationale_list[:3]:
            risk_text.append(Text(f"• {reason}", style="dim"))
    elif include_risk_detail:
        risk_text.append(Text("Insufficient candle data for risk assessment.", style="dim"))

    strat_text = []
    if strategy_risk_level is not None:
        _strat_color = {
            "LOW_RISK": "green",
            "HIGH_RISK": "red",
            "MODERATE": "yellow",
        }.get(strategy_risk_level, "white")
        _strat_sym = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}.get(
            strategy_risk_level, "?"
        )
        strat_text.append(Text(f"Strategy Gate ({strategy_risk_name}): {_strat_sym} {strategy_risk_level}", style=f"bold {_strat_color}"))
        if strategy_risk_level == "HIGH_RISK":
            strat_text.append(Text(f"Strategy '{strategy_risk_name}' signals HIGH_RISK - blocks setup action.", style="red"))
        elif strategy_risk_level == "LOW_RISK":
            strat_text.append(Text(f"✓ Strategy '{strategy_risk_name}' confirms entry signal.", style="green"))
        else:
            strat_text.append(Text(f"~ Strategy '{strategy_risk_name}' is neutral — no override.", style="dim"))

    signal_text = []
    if include_signal_detail and signal_assessment is not None:
        sa = signal_assessment.assessment
        _sig_style = {
            "STRONG": "bold green",
            "MODERATE": "yellow",
            "WEAK": "red",
        }.get(sa.strength.value, "white")
        signal_text.append(Text(
            f"Signal Assessment: {sa.score_label} {sa.strength.value} → {sa.entry_quality.value}",
            style=_sig_style,
        ))
        breakdown = getattr(sa, "breakdown_dict", None) or {}
        if breakdown:
            _factor_labels = {
                "bandar_intensity": "Bandar Intensity",
                "foreign_flow_quality": "Foreign Flow Quality",
                "insider_activity": "Insider Activity",
                "seasonality_edge": "Seasonality Edge",
                "analyst_consensus": "Analyst Consensus",
                "forward_valuation": "Forward Valuation",
            }
            bd_table = compact_table()
            bd_table.add_column("Factor")
            bd_table.add_column("Score", justify="right")
            bd_table.add_column("Source", style="dim")
            for _factor, _score in breakdown.items():
                _source = ""
                if _factor == "foreign_flow_quality" and accum is not None:
                    _source = f"Accum evidence mapped to {_score:.0f}/100"
                bd_table.add_row(
                    _factor_labels.get(_factor, _factor),
                    f"{_score:.1f}",
                    _source,
                )
            signal_text.append(bd_table)
        for line in sa.rationale[-3:]:
            signal_text.append(Text(f"  {line}", style="dim"))
        if signal_assessment.coverage_warning:
            signal_text.append(Text(f"  ⚠ {signal_assessment.coverage_warning}", style="dim yellow"))

    if signal_text:
        console().print("")
        console().print(
            panel(
                Group(*signal_text),
                title="SIGNAL DETAIL",
            )
        )

    if risk_text or strat_text:
        risk_group = []
        if risk_text:
            risk_group.extend(risk_text)
        if strat_text:
            if risk_group:
                risk_group.append(Text(""))
            risk_group.extend(strat_text)
        console().print("")
        console().print(
            panel(
                Group(*risk_group),
                title="RISK DETAIL",
            )
        )

    if regime_text:
        console().print("")
        console().print(
            panel(
                Group(*regime_text),
                title="MARKET DETAIL",
            )
        )

    # ── Panel 4: FLOW / BROKER DETAIL ───────────────────────────────────────
    flow_group = []
    if include_flow_detail and accum:
        label = signal_label(accum, config)
        flow_group.append(Text(f"Accumulation Signal ({window} sessions): {label.upper()}", style="bold cyan"))

        flow_table = compact_table()
        flow_table.add_column("Score")
        flow_table.add_column("Streak")
        flow_table.add_column("Net Days")
        flow_table.add_column("Flow Ratio")
        flow_table.add_column("F_VWAP%")
        flow_table.add_column("VWAP%")
        flow_table.add_column("BB%ile")
        flow_table.add_column("Trend")

        flow_str = f"{accum.avg_flow_ratio:+.1f}%" if accum.avg_flow_ratio is not None else "—"
        fvwap_str = f"{accum.vwap_discount_pct:+.1f}%" if accum.vwap_discount_pct is not None else "—"
        vwap_pct_str = f"{accum.vwap_pct:+.1f}%" if accum.vwap_pct is not None else "—"
        bb_str = f"{int(accum.bb_width_pctile * 100)}%" if accum.bb_width_pctile is not None else "—"
        net_str = f"{accum.net_buy_days}/{accum.total_days}"

        flow_table.add_row(
            f"{accum.score:.1f}",
            f"{accum.consecutive_streak}s",
            net_str,
            flow_str,
            fvwap_str,
            vwap_pct_str,
            bb_str,
            accum.trend
        )
        flow_group.append(flow_table)

        # Corp action risks & flags
        corp_flags = []
        if accum.dividend_risk:
            corp_flags.append(Text("⚠ DIVIDEND RISK — ex-date within hold window", style="yellow"))
        if accum.rights_issue_risk:
            corp_flags.append(Text("⚠ RIGHTS ISSUE — dilution risk within hold window", style="yellow"))
        for rups_detail in accum.upcoming_rups:
            corp_flags.append(Text(f"★ RUPS upcoming — {rups_detail}", style="cyan"))
        if accum.seasonal_edge is not None:
            se = accum.seasonal_edge
            se_color = "green" if se.is_tailwind else ("red" if se.is_headwind else "white")
            corp_flags.append(Text(f"★ SEASONAL {se.label} (score {se.score:+.2f})", style=se_color))
        if accum.insider_buying:
            for label_in in accum.recent_insider_buys:
                corp_flags.append(Text(f"⭐ INSIDER BUY — {label_in}", style="cyan"))
        if accum.analyst_consensus is not None:
            ac = accum.analyst_consensus
            ac_color = "green" if ac.is_bullish and (ac.upside_pct or 0) >= 10 else ("red" if ac.sell_count > ac.buy_count else "white")
            corp_flags.append(Text(f"📊 ANALYST: {ac.label}", style=ac_color))
        if accum.shareholding is not None:
            sh = accum.shareholding
            sh_color = "cyan" if sh.institution_pct >= 30.0 else "white"
            corp_flags.append(Text(f"🏦 HOLDING: {sh.label}", style=sh_color))
        if accum.bandar_detector is not None:
            bd = accum.bandar_detector
            bd_color = "green" if bd.accumulation_score >= 4 else ("yellow" if bd.is_accumulating else ("red" if bd.is_distributing else "white"))
            corp_flags.append(Text(f"🔍 BANDAR: {bd.label}", style=bd_color))
        if accum.fundamentals is not None:
            fund = accum.fundamentals
            fund_color = "green" if fund.is_quality else ("yellow" if fund.roe_ttm is not None and fund.roe_ttm >= 10.0 else "red")
            corp_flags.append(Text(f"📈 FUNDAM: {fund.label}", style=fund_color))

        if corp_flags:
            flow_group.append(Text("\nAdditional Signals & Flags", style="bold cyan"))
            for flag in corp_flags:
                flow_group.append(flag)

    if include_flow_detail and flow_detail:
        if flow_group:
            flow_group.append(Text(""))
        flow_group.append(Text(f"Detailed Flow Context ({flow_detail.window_sessions} sessions) through {fmt_date(flow_detail.through_date)}", style="bold cyan"))

        detail_flow_table = compact_table()
        detail_flow_table.add_column("Range")
        detail_flow_table.add_column("Sessions")
        detail_flow_table.add_column("Net Flow Value")
        detail_flow_table.add_column("Buy/Sell Ratio")
        detail_flow_table.add_column("Streak")
        detail_flow_table.add_column("Avg FLOW%")
        detail_flow_table.add_column("Latest FLOW%")

        latest_flow = fmt_money_short(flow_detail.latest_net_flow) if flow_detail.latest_net_flow is not None else "N/A"
        detail_flow_table.add_row(
            f"{fmt_date(flow_detail.from_date)} → {fmt_date(flow_detail.through_date)}",
            f"{flow_detail.available_sessions}/{flow_detail.window_sessions}",
            f"{fmt_money_short(flow_detail.total_net_flow)} IDR",
            f"{flow_detail.buy_sessions}B / {flow_detail.sell_sessions}S",
            f"{flow_detail.consecutive_buy_sessions}s",
            fmt_pct(flow_detail.avg_flow_ratio_pct, True),
            f"{latest_flow} ({fmt_pct(flow_detail.latest_flow_ratio_pct, True)})"
        )
        flow_group.append(detail_flow_table)

    if include_flow_detail and broker_detail:
        if flow_group:
            flow_group.append(Text(""))
        flow_group.append(Text(f"Attribution ({broker_detail.detail_sessions}/{broker_detail.window_sessions} sessions) via {broker_detail.source}", style="bold cyan"))

        # Side-by-side Buyer/Seller tables
        attribution_table = compact_table()
        attribution_table.add_column("Top Buyers", style="green")
        attribution_table.add_column("Top Sellers", style="red")

        max_len = max(len(broker_detail.top_buyers), len(broker_detail.top_sellers))
        for j in range(max_len):
            buy_str = ""
            if j < len(broker_detail.top_buyers):
                b = broker_detail.top_buyers[j]
                buy_str = f"{b.broker_code}: {fmt_money_short(b.net_value)} ({b.active_sessions}s)"

            sell_str = ""
            if j < len(broker_detail.top_sellers):
                s = broker_detail.top_sellers[j]
                sell_str = f"{s.broker_code}: {fmt_money_short(abs(s.net_value))} ({s.active_sessions}s)"

            attribution_table.add_row(buy_str, sell_str)
        flow_group.append(attribution_table)

        smart_share = f"{broker_detail.smart_share_pct:.1f}%" if broker_detail.smart_share_pct is not None else "N/A"
        buyer_share = f"{broker_detail.top_buyer_share_pct:.1f}%" if broker_detail.top_buyer_share_pct is not None else "N/A"
        seller_share = f"{broker_detail.top_seller_share_pct:.1f}%" if broker_detail.top_seller_share_pct is not None else "N/A"

        metrics_table = compact_table(show_header=False)
        metrics_table.add_column("Metric", style="bold")
        metrics_table.add_column("Value")
        metrics_table.add_row("Smart Money Flow", f"{fmt_money_short_signed(broker_detail.smart_flow)} IDR")
        metrics_table.add_row("Noise Flow", f"{fmt_money_short_signed(broker_detail.noise_flow)} IDR")
        metrics_table.add_row("Weighted Net Flow", f"{fmt_money_short_signed(broker_detail.weighted_net_flow)} IDR")
        metrics_table.add_row("Smart Share %", smart_share)
        metrics_table.add_row("Concentration", f"Top Buyer: {buyer_share} | Top Seller: {seller_share}")
        metrics_table.add_row("Quality Profile", f"{broker_detail.quality} ({broker_detail.broker_weight_quality})")
        flow_group.append(metrics_table)

    if flow_group:
        console().print("")
        console().print(
            panel(
                Group(*flow_group),
                title="FLOW / BROKER DETAIL",
            )
        )

    # ── Panel 5: STRATEGY EVIDENCE ──────────────────────────────────────────
    history_group = []
    if include_strategy and backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        history_group.append(Text(f"Historical Backtest ({strategy_name}): {r.trade_count} trades", style="bold cyan"))
        history_group.append(Text("Evidence only: this panel does not change TradeSetup.action.", style="dim"))
        period_start = getattr(r, "start_date", None)
        period_end = getattr(r, "end_date", None)
        period_text = (
            f"{period_start} to {period_end}"
            if period_start is not None and period_end is not None
            else "unknown"
        )
        hist_table = compact_table(show_header=False)
        hist_table.add_column("Metric", style="bold")
        hist_table.add_column("Value")

        win_style = "green" if float(r.win_rate) >= 55 else ("yellow" if float(r.win_rate) >= 45 else "red")
        avg_win_val = f"{float(r.avg_win):,.0f} IDR" if r.avg_win else "—"
        avg_loss_val = f"{float(r.avg_loss):,.0f} IDR" if r.avg_loss else "—"

        hist_table.add_row("Period", period_text)
        hist_table.add_row("Win Rate", f"[{win_style}]{float(r.win_rate):.1f}%[/]")
        hist_table.add_row("Profit Factor", f"{float(r.profit_factor):.2f}")
        hist_table.add_row("Max Drawdown", f"{float(r.max_drawdown_pct):.1f}%")
        hist_table.add_row("Avg Win/Loss", f"{avg_win_val} / {avg_loss_val}")
        history_group.append(hist_table)
    elif include_strategy and backtest_result is not None and backtest_result.trade_count == 0:
        history_group.append(Text(f"Historical Backtest ({strategy_name})", style="bold cyan"))
        if getattr(backtest_result, "start_date", None) is not None and getattr(backtest_result, "end_date", None) is not None:
            history_group.append(Text(
                f"Period: {backtest_result.start_date} to {backtest_result.end_date}",
                style="dim",
            ))
        history_group.append(Text("No trades triggered in available history (needs more broker data).", style="dim"))
        history_group.append(Text(f"Tip: run `saham backtest {ticker} --strategy {strategy_name} --verbose`", style="dim italic"))
    elif include_strategy:
        history_group.append(Text("Historical Backtest", style="bold cyan"))
        history_group.append(Text(f"Could not run backtest. Run: `saham fetch market {ticker} --days 730`", style="dim yellow"))

    if history_group:
        console().print("")
        console().print(
            panel(
                Group(*history_group),
                title="STRATEGY EVIDENCE",
            )
        )

    # ── Panel 6: SENTIMENT EVIDENCE ─────────────────────────────────────────
    if include_sentiment:
        sentiment_group = []
        if sentiment_resp and not sentiment_resp.warning:
            snap = sentiment_resp.snapshot
            call_val = snap.overall_sentiment.value.upper()
            call_style = "green" if call_val == "POSITIVE" else ("red" if call_val == "NEGATIVE" else "yellow")

            sentiment_group.append(Text(f"News Sentiment (3d): [{call_style}]{call_val}[/]", style="bold cyan"))
            sentiment_group.append(Text(
                f"Headlines scanned: {snap.total_count} (+{snap.positive_count} / ={snap.neutral_count} / -{snap.negative_count}) | "
                f"Confidence: {snap.confidence_pct}%"
            ))
        else:
            sentiment_group.append(Text("News Sentiment (3d)", style="bold cyan"))
            msg = sentiment_warning or "News unavailable (no network or fetch failed)."
            sentiment_group.append(Text(msg, style="dim"))
            if not sentiment_verbose:
                sentiment_group.append(Text("Use --sentiment-verbose to show provider details.", style="dim italic"))

        console().print("")
        console().print(
            panel(
                Group(*sentiment_group),
                title="SENTIMENT EVIDENCE",
            )
        )
    console().print("")


def _fmt_pct_compare(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def display_swing_compare(
    rows: list[tuple[str, SwingBacktestResponse]],
    start_date: date,
    end_date: date,
    universe_label: str,
    variants_by_name: dict[str, tuple[str, ...]],
) -> None:
    # Metadata panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    cost_bps = rows[0][1].cost_bps if rows else Decimal("0")
    meta_table.add_row("Universe", universe_label.upper())
    meta_table.add_row("Period", f"{start_date} to {end_date}")
    meta_table.add_row("Commission Cost", f"{float(cost_bps):g} bps one-way")

    console().print("")
    console().print(
        panel(
            meta_table,
            title="SWING BACKTEST COMPARISON",
        )
    )

    # Comparison Grid
    compare_table = compact_table()
    compare_table.add_column("Variant", style="bold yellow")
    compare_table.add_column("Regimes", style="cyan")
    compare_table.add_column("Trades", justify="right")
    compare_table.add_column("Return", justify="right")
    compare_table.add_column("Max DD", justify="right")
    compare_table.add_column("Win", justify="right")
    compare_table.add_column("PF", justify="right")
    compare_table.add_column("Skip Reg", justify="right")
    compare_table.add_column("Exposure", justify="right")

    for name, response in rows:
        regimes = variants_by_name[name]
        regime_label = "all" if not regimes else ",".join(regimes)
        profit_factor = (
            "INF" if response.profit_factor == float("inf")
            else "N/A" if response.profit_factor is None
            else f"{response.profit_factor:.2f}"
        )

        ret_val = response.total_return_pct
        ret_color = "green" if (ret_val or 0) >= 0 else "red"
        ret_str = f"[{ret_color}]{_fmt_pct_compare(ret_val, True)}[/]"

        dd_val = response.max_drawdown_pct
        dd_str = f"[red]{_fmt_pct_compare(dd_val, True)}[/]" if dd_val is not None else "N/A"

        win_val = response.win_rate_pct
        win_color = "green" if (win_val or 0) >= 55.0 else ("yellow" if (win_val or 0) >= 45.0 else "red")
        win_str = f"[{win_color}]{_fmt_pct_compare(win_val)}[/]" if win_val is not None else "N/A"

        compare_table.add_row(
            name,
            regime_label,
            str(response.trade_count),
            ret_str,
            dd_str,
            win_str,
            profit_factor,
            str(response.skipped_by_regime),
            _fmt_pct_compare(response.exposure_pct)
        )

    console().print(compare_table)
    console().print(Text("\nDISCLAIMER: Historical simulation only. Not trading advice.", style="dim italic"))
    console().print("")
