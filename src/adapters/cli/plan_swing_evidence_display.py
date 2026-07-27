"""
Detailed evidence / full-output rendering for saham analyze swing.

Layer: Adapter

This module must not change what evidence is included, must not change
market-context canonical/preview wording, and must not decide final action.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.plan_swing_corporate_calendar_display import (
    print_corporate_calendar_panel,
)
from src.adapters.cli.plan_swing_flow_detail_display import print_flow_detail_panel
from src.adapters.cli.plan_swing_formatters import fmt_pct
from src.adapters.cli.plan_swing_institutional_display import (
    print_institutional_accumulation_section,
)
from src.adapters.cli.plan_swing_output_context import SwingOutputDisplayContext
from src.adapters.cli.plan_swing_overview_display import (
    print_swing_rich_overview,
    setup_gates_group,
)
from src.adapters.cli.plan_swing_sector_context_display import print_sector_context_panel
from src.adapters.cli.plan_swing_sentiment_display import print_sentiment_evidence_panel
from src.adapters.cli.plan_swing_signal_detail_display import (
    print_alpha_trigger_detail_panel,
    print_signal_detail_panel,
)
from src.adapters.cli.plan_swing_strategy_evidence_display import (
    print_strategy_evidence_panel,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
    context_factor_value,
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
    regime_confidence = getattr(market_regime, "regime_confidence", None)
    regime_stability = getattr(market_regime, "regime_stability", None)
    days_in = getattr(market_regime, "days_in_regime", None)

    regime_line = Text()
    regime_line.append(f"Regime: {regime_label}", style="bold cyan")
    if regime_confidence is not None:
        conf_style = (
            "green"
            if regime_confidence >= 0.65
            else "yellow"
            if regime_confidence >= 0.35
            else "bold red"
        )
        regime_line.append("  conf: ", style="dim")
        regime_line.append(f"{regime_confidence:.2f}", style=conf_style)
    if regime_stability is not None:
        stab_style = (
            "green"
            if regime_stability == "STABLE"
            else "yellow"
            if regime_stability == "UNKNOWN"
            else "red"
        )
        regime_line.append(f"  [{regime_stability}]", style=stab_style)
    if days_in is not None:
        regime_line.append(f"  {days_in}d", style="dim")
    items.append(regime_line)

    transition_warning = getattr(market_regime, "transition_warning", None)
    if transition_warning:
        items.append(Text(f"  ⚠ {transition_warning}", style="yellow"))

    # ADR-037: canonical signal already includes regime conditioning.
    # preview_signal == canonical_signal — no separate "signal delta" to show.
    # Regime impact is visible in signal rationale (see --with-signal-detail).
    if canonical_signal is not None:
        score = canonical_signal.assessment.score
        eq = canonical_signal.assessment.entry_quality.value
        bd_dict = dict(canonical_signal.assessment.breakdown)
        if bd_dict.get("regime_conditioning"):
            regime_label_sig = REGIME_DISPLAY_LABEL.get(
                market_regime.regime.value, market_regime.regime.value
            )
            note = f"{regime_label_sig} conditioning applied — score {score:.0f} ({eq})"
            items.append(Text(f"Signal:         {note}", style="yellow"))
        else:
            items.append(
                Text(
                    f"Signal:         score {score:.0f} ({eq}) — no regime conditioning fired",
                    style="dim",
                )
            )

    if canonical_risk is not None and preview_risk is not None:
        raw_gate = canonical_risk.assessment.gate_triggered
        preview_gate = preview_risk.assessment.gate_triggered
        if preview_gate and not raw_gate:
            items.append(
                Text(f"Risk preview:   regime gate would trigger ({preview_gate})", style="yellow")
            )
        elif preview_gate and raw_gate and preview_gate != raw_gate:
            items.append(
                Text(f"Risk preview:   gate upgraded {raw_gate} → {preview_gate}", style="yellow")
            )
        else:
            items.append(Text("Risk preview:   no additional gate triggered", style="dim"))

    canonical_action = canonical_trade_setup.action.value if canonical_trade_setup else "N/A"
    preview_action = preview_trade_setup.action.value
    if canonical_action != preview_action:
        items.append(
            Text(
                f"Preview:        TradeSetup risk-preview → {preview_action} "
                f"(vs canonical {canonical_action})",
                style="bold yellow",
            )
        )
    else:
        items.append(
            Text("Preview:        No action change under regime-adjusted risk.", style="dim green")
        )
    items.append(Text(f"Canonical:      {canonical_action}", style="bold"))

    return Group(*items)


def print_market_context_preview_panel(ctx: SwingOutputDisplayContext) -> None:
    market_regime = ctx.verdict.market_regime
    market_context_trade_setup_preview = ctx.verdict.market_context_trade_setup_preview
    if market_context_trade_setup_preview is not None and market_regime is not None:
        _preview_group = _market_context_preview_group(
            market_regime=market_regime,
            canonical_signal=ctx.verdict.signal_assessment,
            preview_signal=ctx.verdict.market_context_signal_preview,
            canonical_risk=ctx.verdict.risk_response,
            preview_risk=ctx.verdict.market_context_risk_preview,
            canonical_trade_setup=ctx.verdict.trade_setup,
            preview_trade_setup=market_context_trade_setup_preview,
        )
        console().print("")
        console().print(
            panel(
                _preview_group,
                title="MARKET CONTEXT PREVIEW",
                subtitle="regime conditioning in canonical signal · risk preview via MCE",
            )
        )


def print_setup_evidence_panel(ctx: SwingOutputDisplayContext) -> None:
    setup_eval = ctx.evidence.setup_eval
    if setup_eval is not None:
        console().print("")
        console().print(
            panel(
                setup_gates_group(setup_eval, ctx.diagnostics.broker_quality_note),
                title="SETUP EVIDENCE",
            )
        )


def print_market_detail_panel(ctx: SwingOutputDisplayContext) -> None:
    market_regime = ctx.verdict.market_regime
    regime_text = []
    if ctx.options.include_market_detail and market_regime is not None:
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

    if regime_text:
        console().print("")
        console().print(
            panel(
                Group(*regime_text),
                title="MARKET DETAIL",
            )
        )


def print_risk_detail_panel(ctx: SwingOutputDisplayContext) -> None:
    risk_resp = ctx.verdict.risk_response
    risk_text = []
    if ctx.options.include_risk_detail and risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        if r.gate_triggered:
            _status = f"BLOCKED — gate {r.gate_triggered} (conf {r.gate_confidence or 0}/100)"
        else:
            _status = "OPEN — no gate fired"
        risk_text.append(Text(f"Risk Status: {_status}", style="bold cyan"))
        risk_table = compact_table()
        risk_table.add_column("SMA20")
        risk_table.add_column("EMA20")
        risk_table.add_column("RSI14")
        risk_table.add_row(
            f"{float(snap.sma):,.0f}", f"{float(snap.ema):,.0f}", f"{float(snap.rsi):.1f}"
        )
        risk_text.append(risk_table)
        for reason in r.rationale_list[:3]:
            risk_text.append(Text(f"• {reason}", style="dim"))
    elif ctx.options.include_risk_detail:
        risk_text.append(Text("Insufficient candle data for risk assessment.", style="dim"))

    if risk_text:
        console().print("")
        console().print(
            panel(
                Group(*risk_text),
                title="RISK DETAIL",
            )
        )


def print_swing_output(ctx: SwingOutputDisplayContext) -> None:
    # Print the primary Decision Dashboard Panel (Panel 1)
    print_swing_rich_overview(
        ticker=ctx.ticker,
        today=ctx.today,
        strategy_name=ctx.strategy_name,
        data_freshness=ctx.diagnostics.data_freshness,
        broker_detail=ctx.diagnostics.broker_detail,
        accum=ctx.evidence.accumulation_candidate,
        risk_resp=ctx.verdict.risk_response,
        atr_value=ctx.atr_value,
        sizing=ctx.sizing,
        setup_eval=ctx.evidence.setup_eval,
        setup_sizing=ctx.setup_sizing,
        broker_quality_note=ctx.diagnostics.broker_quality_note,
        market_regime=ctx.verdict.market_regime,
        capital=ctx.capital,
        backtest_result=ctx.evidence.backtest_result,
        sentiment_resp=ctx.evidence.sentiment_response,
        sentiment_warning=ctx.evidence.sentiment_warning,
        config=ctx.config,
        include_strategy=ctx.options.include_strategy,
        include_sentiment=ctx.options.include_sentiment,
        include_flow_detail=ctx.options.include_flow_detail,
        include_signal_detail=ctx.options.include_signal_detail,
        include_risk_detail=ctx.options.include_risk_detail,
        include_market_detail=ctx.options.include_market_detail,
        signal_assessment=ctx.verdict.signal_assessment,
        trade_setup=ctx.verdict.trade_setup,
        market_context_signal_preview=ctx.verdict.market_context_signal_preview,
        market_context_risk_preview=ctx.verdict.market_context_risk_preview,
        market_context_trade_setup_preview=ctx.verdict.market_context_trade_setup_preview,
        with_technical_gate=ctx.options.with_technical_gate,
        sector_context_evidence=ctx.evidence.sector_context_evidence,
        signal_assessment_availability=ctx.verdict.signal_assessment_availability,
        effective_session=ctx.effective_session,
    )

    print_market_context_preview_panel(ctx)
    print_setup_evidence_panel(ctx)
    print_signal_detail_panel(ctx)
    print_alpha_trigger_detail_panel(ctx)
    print_risk_detail_panel(ctx)
    print_market_detail_panel(ctx)
    print_sector_context_panel(ctx)

    if (
        ctx.options.include_flow_detail
        and ctx.evidence.institutional_accumulation_evidence is not None
    ):
        print_institutional_accumulation_section(ctx.evidence.institutional_accumulation_evidence)

    print_flow_detail_panel(ctx)
    print_strategy_evidence_panel(ctx)
    print_sentiment_evidence_panel(ctx)
    print_corporate_calendar_panel(ctx)
    console().print("")
