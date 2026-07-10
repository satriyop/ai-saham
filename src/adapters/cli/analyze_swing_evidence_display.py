"""
Detailed evidence / full-output rendering for saham analyze swing.

Layer: Adapter

This module must not change what evidence is included, must not change
market-context canonical/preview wording, and must not decide final action.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    fmt_money_short,
    fmt_money_short_signed,
)
from src.adapters.cli.analyze_swing_formatters import (
    SwingDisplayConfig,
    flow_direction_label,
    fmt_date,
    fmt_pct,
    foreign_flow_evidence_label,
)
from src.adapters.cli.analyze_swing_overview_display import (
    flow_trigger_blocked_text,
    print_swing_rich_overview,
    setup_gates_group,
)
from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.view_market_context_display import (
    REGIME_DISPLAY_LABEL,
    context_conviction_score,
    context_factor_value,
)
from src.domain.value_objects.alpha_trigger_score import (
    AlphaTriggerScore,
    EvidenceAuthorityStatus,
)
from src.domain.value_objects.institutional_accumulation_evidence import (
    InstitutionalAccumulationEvidence,
)
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence

if TYPE_CHECKING:
    from src.domain.value_objects.strategy_evidence import StrategyEvidence


def has_current_flow_confirmation(candidate: Any) -> bool:
    flow = getattr(candidate, "avg_flow_ratio", None)
    return (
        flow is not None
        and flow > 0
        and getattr(candidate, "consecutive_streak", 0) > 0
        and getattr(candidate, "net_buy_days", 0) > (getattr(candidate, "total_days", 0) / 2)
    )


def has_bandar_distribution(snapshot: Any) -> bool:
    if snapshot is None:
        return False
    if getattr(snapshot, "is_distributing", False):
        return True
    broker_accdist = str(getattr(snapshot, "broker_accdist", "") or "").lower()
    return broker_accdist in {"dis", "dist"}


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
    regime_stability  = getattr(market_regime, "regime_stability", None)
    days_in           = getattr(market_regime, "days_in_regime", None)

    regime_line = Text()
    regime_line.append(f"Regime: {regime_label}", style="bold cyan")
    if regime_confidence is not None:
        conf_style = "green" if regime_confidence >= 0.65 else "yellow" if regime_confidence >= 0.35 else "bold red"
        regime_line.append(f"  conf: ", style="dim")
        regime_line.append(f"{regime_confidence:.2f}", style=conf_style)
    if regime_stability is not None:
        stab_style = "green" if regime_stability == "STABLE" else "yellow" if regime_stability == "UNKNOWN" else "red"
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
            items.append(Text(
                f"Signal:         score {score:.0f} ({eq}) — no regime conditioning fired",
                style="dim",
            ))

    if canonical_risk is not None and preview_risk is not None:
        raw_gate = canonical_risk.assessment.gate_triggered
        preview_gate = preview_risk.assessment.gate_triggered
        if preview_gate and not raw_gate:
            items.append(Text(f"Risk preview:   regime gate would trigger ({preview_gate})", style="yellow"))
        elif preview_gate and raw_gate and preview_gate != raw_gate:
            items.append(Text(f"Risk preview:   gate upgraded {raw_gate} → {preview_gate}", style="yellow"))
        else:
            items.append(Text("Risk preview:   no additional gate triggered", style="dim"))

    canonical_action = canonical_trade_setup.action.value if canonical_trade_setup else "N/A"
    preview_action = preview_trade_setup.action.value
    if canonical_action != preview_action:
        items.append(Text(
            f"Preview:        TradeSetup risk-preview → {preview_action} (vs canonical {canonical_action})",
            style="bold yellow",
        ))
    else:
        items.append(Text("Preview:        No action change under regime-adjusted risk.", style="dim green"))
    items.append(Text(f"Canonical:      {canonical_action}", style="bold"))

    return Group(*items)


def _fmt_ia(v: float | None, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}" if v is not None else "—"


def _ia_panel_group(ev: InstitutionalAccumulationEvidence) -> list:
    items: list = []
    items.append(Text("DIAGNOSTIC — no scoring authority", style="dim"))

    ft = ev.foreign_institutional_track
    domestic_has_data = ev.domestic_bandar_track.coverage_score > 0.0
    foreign_has_data = ft.coverage_score > 0.0

    if not foreign_has_data and not domestic_has_data and ev.unavailable_reasons:
        for reason in list(ev.unavailable_reasons)[:3]:
            items.append(Text(f"  ⚠ {reason}", style="dim yellow"))
        return items

    items.append(Text("Foreign Institutional Track", style="bold cyan"))
    ft_table = compact_table(show_header=False)
    ft_table.add_column("Metric", style="bold")
    ft_table.add_column("Value")
    ft_table.add_row("Coverage", _fmt_ia(ft.coverage_score))
    ft_table.add_row("Conviction", _fmt_ia(ft.conviction_score))
    ft_table.add_row("Foreign participation", _fmt_ia(ft.foreign_participation_score))
    ft_table.add_row("CR4", _fmt_ia(ft.foreign_cr4_score))
    ft_table.add_row("CR8", _fmt_ia(ft.foreign_cr8_score))
    ft_table.add_row("CNFB divergence", _fmt_ia(ft.cnfb_divergence_score))
    ft_table.add_row("Foreign VWAP distance", _fmt_ia(ft.foreign_vwap_distance_score))
    items.append(ft_table)

    dt = ev.domestic_bandar_track
    items.append(Text(""))
    items.append(Text("Domestic Bandar Track", style="bold cyan"))
    dt_table = compact_table(show_header=False)
    dt_table.add_column("Metric", style="bold")
    dt_table.add_column("Value")
    dt_table.add_row("Coverage", _fmt_ia(dt.coverage_score))
    dt_table.add_row("Conviction", _fmt_ia(dt.conviction_score))
    dt_table.add_row("Broker consistency", _fmt_ia(dt.broker_consistency_score))
    dt_table.add_row("Broker reversal", _fmt_ia(dt.broker_reversal_score))
    dt_table.add_row("Accum session ratio", _fmt_ia(dt.accumulation_session_ratio))
    dt_table.add_row("Domestic buy VWAP dist", _fmt_ia(dt.domestic_buy_vwap_distance_score))
    dt_table.add_row("Broker HHI divergence", _fmt_ia(dt.broker_hhi_divergence_score))
    dt_table.add_row("Bandar broad", _fmt_ia(dt.bandar_broad_score_normalized))
    if dt.bandar_accumulation_score_normalized is not None:
        dt_table.add_row("Bandar accumulation", _fmt_ia(dt.bandar_accumulation_score_normalized))
    items.append(dt_table)

    ct = ev.counterparty_transfer
    if ct is not None:
        items.append(Text(""))
        items.append(Text("Counterparty Transfer", style="bold cyan"))
        ct_table = compact_table(show_header=False)
        ct_table.add_column("Metric", style="bold")
        ct_table.add_column("Value")
        ct_table.add_row("Transfer asymmetry", _fmt_ia(ct.transfer_asymmetry_score))
        ct_table.add_row("Buy-side HHI", _fmt_ia(ct.buy_side_hhi, 4))
        ct_table.add_row("Sell-side HHI", _fmt_ia(ct.sell_side_hhi, 4))
        items.append(ct_table)

    return items


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
    signal_assessment=None,
    trade_setup=None,
    market_context_signal_preview=None,
    market_context_risk_preview=None,
    market_context_trade_setup_preview=None,
    config: SwingDisplayConfig | None = None,
    with_technical_gate: bool = False,
    sector_context_evidence: "SectorContextEvidence | None" = None,
    institutional_accumulation_evidence: "InstitutionalAccumulationEvidence | None" = None,
    strategy_evidence: "StrategyEvidence | None" = None,
) -> None:
    # Rescaled 0-120 -> 0-100 (see ADR-039). Note: these literals already
    # didn't match swing_config.py's canonical defaults before the rescale
    # (a pre-existing drift, not introduced here) — converted proportionally
    # but not unified with swing_config.py, which is unrelated cleanup.
    config = config or SwingDisplayConfig(
        enter_min_score=58.3,
        watch_min_score=41.7,
        coiled_spring_bb_pctile=0.2,
        coiled_spring_min_score=58.3,
        strong_min_score=66.7,
        strong_min_streak=3,
        building_min_score=50.0,
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
        sector_context_evidence=sector_context_evidence,
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
                subtitle="regime conditioning in canonical signal · risk preview via MCE",
            )
        )

    # ── Panel 2: SETUP EVIDENCE ─────────────────────────────────────────────
    if setup_eval is not None:
        console().print("")
        console().print(
            panel(
                setup_gates_group(setup_eval, broker_quality_note),
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
            _status = f"BLOCKED — gate {r.gate_triggered} (conf {r.gate_confidence or 0}/100)"
        else:
            _status = "OPEN — no gate fired"
        risk_text.append(Text(f"Risk Status: {_status}", style="bold cyan"))
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

    signal_text = []
    if include_signal_detail and signal_assessment is not None:
        sa = signal_assessment.assessment
        _sig_style = {
            "STRONG": "bold green",
            "MODERATE": "yellow",
            "WEAK": "red",
        }.get(sa.strength.value, "white")
        evidence_coverage = (
            getattr(sa, "coverage_score", None)
            or getattr(signal_assessment, "evidence_confidence", None)
            or 1.0
        )
        signal_text.append(Text(
            f"Explains the Signal column in Verdict: {sa.score_label} "
            f"{sa.strength.value} / {evidence_coverage:.0%} coverage "
            f"-> {sa.entry_quality.value}",
            style=_sig_style,
        ))
        signal_text.append(Text(
            "Scale: SignalEngine 0-100. Used in final TradeSetup: yes.",
            style="dim",
        ))
        breakdown = getattr(sa, "breakdown_dict", None) or {}
        active_flags = getattr(signal_assessment, "active_flags", ())
        flag_adj = getattr(signal_assessment, "flag_adjustment", 0)
        raw_score = getattr(signal_assessment, "raw_group_score", None)
        conf = getattr(signal_assessment, "evidence_confidence", None)
        if breakdown:
            _group_labels = {
                "setup_quality_group": "Setup Quality",
                "flow_confirmation_group": "Flow Confirmation",
                "evidence_confidence": "Evidence Coverage",
                "flag_adjustment": "Flag Adjustment",
            }
            _group_sources = {
                "setup_quality_group": "SetupEvidence.match_strength (MATCH=100, PARTIAL=60, NO_MATCH=20)",
                "flow_confirmation_group": "FlowConfirmationEvidence.capped_strength × 100",
                "evidence_confidence": "coverage: present weight / total weight (60% Setup + 40% Flow)",
                "flag_adjustment": "sum of active flag penalties",
            }
            bd_table = compact_table()
            bd_table.add_column("Group")
            bd_table.add_column("Value", justify="right")
            bd_table.add_column("Source", style="dim")
            for _key, _val in breakdown.items():
                _label = _group_labels.get(_key, _key)
                _source = _group_sources.get(_key, "")
                if _key == "evidence_confidence":
                    bd_table.add_row(_label, f"{_val:.0f}%", _source)
                else:
                    bd_table.add_row(_label, f"{_val:.1f}", _source)
            signal_text.append(bd_table)
        if active_flags:
            _flag_names = {
                "VALUATION_STRETCHED": f"VALUATION_STRETCHED ({flag_adj:+d} pts total)",
                "ANALYST_BEARISH": "ANALYST_BEARISH",
                "INSIDER_SELLING": "INSIDER_SELLING",
            }
            flag_detail = ", ".join(_flag_names.get(f, f) for f in active_flags)
            signal_text.append(Text(f"  Flags: {flag_detail}", style="dim yellow"))
        if raw_score is not None and flag_adj != 0:
            signal_text.append(Text(
                f"  Raw group score {raw_score} + flag adjustment {flag_adj:+d} = {sa.score}",
                style="dim",
            ))
        if conf is not None:
            signal_text.append(Text(
                f"  Evidence confidence: {conf:.0%} of scoring weight covered",
                style="dim",
            ))
        for line in sa.rationale[-3:]:
            signal_text.append(Text(f"  {line}", style="dim"))
        if signal_assessment.coverage_warning:
            signal_text.append(Text(f"  ⚠ {signal_assessment.coverage_warning}", style="dim yellow"))
        constraints = getattr(sa, "decision_constraints", None)
        if constraints is not None:
            signal_text.append(Text("  Decision constraints", style="bold cyan"))
            signal_text.append(Text(
                f"    max_decision={constraints.max_decision} "
                f"regime={constraints.regime or 'none'} "
                f"enter_allowed={constraints.regime_enter_allowed} "
                f"size={constraints.effective_size_multiplier:.2f}",
                style="dim",
            ))
            if constraints.setup_family or constraints.setup_regime_action:
                signal_text.append(Text(
                    f"    setup={constraints.setup_family or 'none'} "
                    f"action={constraints.setup_regime_action or 'none'}",
                    style="dim",
                ))
            for reason in constraints.constraint_reasons:
                signal_text.append(Text(f"    - {reason}", style="dim yellow"))

    if signal_text:
        console().print("")
        console().print(
            panel(
                Group(*signal_text),
                title="SIGNAL DETAIL",
            )
        )

    # ── Alpha/Trigger Detail ─────────────────────────────────────────────────
    alpha_trigger_text = []
    if include_signal_detail and signal_assessment is not None:
        ats: AlphaTriggerScore | None = getattr(signal_assessment, "alpha_trigger_score", None)
        if ats is not None:
            alpha_wt_pct = int(ats.alpha_weight * 100)
            trigger_wt_pct = 100 - alpha_wt_pct
            alpha_s = f"{ats.alpha_score:.1f}" if ats.alpha_score is not None else "—"
            trig_s = f"{ats.trigger_score:.1f}" if ats.trigger_score is not None else "—"
            final_s = f"{ats.final_exact_score:.1f}" if ats.final_exact_score is not None else "—"
            alpha_trigger_text.append(Text(
                f"α {alpha_s}  trigger {trig_s}  final {final_s}  "
                f"horizon {ats.horizon}  "
                f"alpha {alpha_wt_pct}% · trigger {trigger_wt_pct}%",
                style="bold cyan",
            ))
            alpha_trigger_text.append(Text(
                f"coverage {ats.coverage_score:.2f}  authority {ats.authority_coverage_score:.2f}  "
                f"conviction {ats.conviction_score:.2f}  "
                f"flow_trigger {'✓ allowed' if ats.flow_trigger_allowed else '✗ blocked'}",
                style="dim",
            ))
            if ats.group_contributions:
                ct = compact_table()
                ct.add_column("Group")
                ct.add_column("Score", justify="right")
                ct.add_column("Present")
                ct.add_column("Status")
                ct.add_column("CfgWt", justify="right")
                ct.add_column("EffWt", justify="right")
                ct.add_column("AlphaWtd", justify="right")
                ct.add_column("TrigWtd", justify="right")
                ct.add_column("TrigOK")
                for c in ats.group_contributions:
                    is_diag = (
                        c.evidence_status == EvidenceAuthorityStatus.DIAGNOSTIC
                        or c.effective_weight == 0.0
                    )
                    status_text = Text(
                        c.evidence_status.value + (" — no weight" if is_diag else ""),
                        style="dim" if is_diag else "",
                    )
                    eff_wt_text = Text(f"{c.effective_weight:.3f}", style="dim" if is_diag else "")
                    ct.add_row(
                        Text(c.group, style="dim" if is_diag else ""),
                        Text(f"{c.score:.1f}" if c.present else "—", style="dim" if is_diag else ""),
                        Text("✓" if c.present else "✗", style="dim" if is_diag else ""),
                        status_text,
                        Text(f"{c.configured_weight:.3f}", style="dim" if is_diag else ""),
                        eff_wt_text,
                        Text(f"{c.alpha_weighted:.3f}", style="dim" if is_diag else ""),
                        Text(f"{c.trigger_weighted:.3f}", style="dim" if is_diag else ""),
                        Text("✓" if c.trigger_allowed else "✗", style="dim" if is_diag else ""),
                    )
                alpha_trigger_text.append(ct)
                for c in ats.group_contributions:
                    if c.group == "institutional_flow" and not c.trigger_allowed:
                        for reason in c.reasons:
                            text = flow_trigger_blocked_text(reason)
                            if text is not None:
                                alpha_trigger_text.append(
                                    Text(f"  {text}", style="dim yellow")
                                )
            for reason in list(ats.unavailable_reasons)[-3:]:
                alpha_trigger_text.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if alpha_trigger_text:
        console().print("")
        console().print(panel(Group(*alpha_trigger_text), title="ALPHA/TRIGGER DETAIL"))

    if risk_text:
        console().print("")
        console().print(
            panel(
                Group(*risk_text),
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

    # ── Sector Context Detail ────────────────────────────────────────────────
    sc_text = []
    if include_market_detail and sector_context_evidence is not None:
        sc = sector_context_evidence
        if sc.peer_count == 0 and sc.sector_regime == "UNKNOWN" and sc.unavailable_reasons:
            for reason in list(sc.unavailable_reasons)[:2]:
                sc_text.append(Text(f"Sector context unavailable: {reason}", style="dim"))
        else:
            _regime_style = {
                "BULLISH": "bold green",
                "BEARISH": "bold red",
                "NEUTRAL": "yellow",
                "UNKNOWN": "dim",
            }.get(sc.sector_regime, "white")
            header = Text()
            header.append(f"Sector: {sc.sector or '—'}  ", style="bold")
            header.append("Regime: ")
            header.append(sc.sector_regime, style=_regime_style)
            header.append(f"  Peers: {sc.peer_count}")
            sc_text.append(header)

            def _spct(v: float | None) -> str:
                return f"{v * 100:+.1f}%" if v is not None else "—"

            mt = compact_table()
            mt.add_column("Sector 20d")
            mt.add_column("vs IHSG")
            mt.add_column("Breadth")
            mt.add_column("vs Sector RS")
            mt.add_row(
                _spct(sc.sector_20d_return),
                _spct(sc.sector_vs_ihsg_20d),
                f"{sc.sector_breadth:.0%}" if sc.sector_breadth is not None else "—",
                _spct(sc.ticker_vs_sector_rs),
            )
            sc_text.append(mt)

            peer_tickers = list(sc.peer_tickers)
            if peer_tickers:
                shown = ", ".join(peer_tickers[:3])
                suffix = " …" if len(peer_tickers) > 3 else ""
                sc_text.append(Text(f"  Peers ({sc.peer_count}): {shown}{suffix}", style="dim"))

            sc_text.append(Text(
                f"  Coverage: {sc.coverage_score:.2f}  DIAGNOSTIC — no scoring impact",
                style="dim",
            ))
            for reason in list(sc.unavailable_reasons)[:2]:
                sc_text.append(Text(f"  ⚠ {reason}", style="dim yellow"))

    if sc_text:
        console().print("")
        console().print(panel(Group(*sc_text), title="SECTOR CONTEXT"))

    # ── Institutional Accumulation Detail ────────────────────────────────────
    if include_flow_detail and institutional_accumulation_evidence is not None:
        ia_items = _ia_panel_group(institutional_accumulation_evidence)
        console().print("")
        console().print(panel(Group(*ia_items), title="INSTITUTIONAL ACCUMULATION"))

    # ── Panel 4: FLOW / BROKER DETAIL ───────────────────────────────────────
    flow_group = []
    if include_flow_detail and accum:
        evidence_label = foreign_flow_evidence_label(accum, config)
        flow_label = flow_direction_label(accum)
        flow_group.append(Text(
            f"Composite Foreign Flow Score ({window} broker sessions): "
            f"{evidence_label.upper()} / {flow_label.upper()}",
            style="bold cyan",
        ))
        flow_group.append(Text(
            "Scope: broker-flow and attribution diagnostics. SignalEngine uses the composite foreign-flow score below, not pure foreign net flow.",
            style="dim",
        ))
        flow_group.append(Text(
            "Longer-term flow context below is diagnostic only and does not directly change Verdict.",
            style="dim",
        ))

        flow_table = compact_table()
        flow_table.add_column("Foreign Flow Score")
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
            f"{accum.foreign_flow_score:.1f}",
            f"{accum.consecutive_streak}s",
            net_str,
            flow_str,
            fvwap_str,
            vwap_pct_str,
            bb_str,
            accum.trend
        )
        flow_group.append(flow_table)

        if accum.foreign_flow_score >= config.watch_min_score and not has_current_flow_confirmation(accum):
            flow_group.append(Text(
                "Note: composite score is in watch-zone, but current foreign flow is not confirming "
                "(check Flow Ratio, Streak, and Net Days).",
                style="dim yellow",
            ))

        bd_for_note = getattr(accum, "bandar_detector", None)
        if has_bandar_distribution(bd_for_note):
            flow_group.append(Text(
                "Note: Bandar detector shows distribution; RiskEngine can block execution even when "
                "the composite Signal remains MODERATE.",
                style="dim red",
            ))

        score_breakdown = getattr(accum, "foreign_flow_score_breakdown", None)
        breakdown = getattr(score_breakdown, "breakdown_dict", None) or {}
        if breakdown:
            component_labels = {
                "cons": "Net-day consistency",
                "streak": "Buy streak",
                "vwap": "Foreign VWAP discount",
                "rsi": "RSI headroom",
                "flow": "Flow ratio",
                "bb": "BB squeeze",
                "inst": "Broker attribution",
            }
            component_table = compact_table()
            component_table.add_column("Foreign Flow Component")
            component_table.add_column("Pts", justify="right")
            for key, value in breakdown.items():
                component_table.add_row(
                    component_labels.get(key, key),
                    f"{value:.1f}",
                )
            flow_group.append(component_table)

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
            corp_flags.append(Text(f"★ SEASONAL {se.label} (accum bonus {se.score:+.2f})", style=se_color))
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
        flow_group.append(Text(
            f"Longer-Term Flow Context ({flow_detail.window_sessions} broker sessions, diagnostic only) through {fmt_date(flow_detail.through_date)}",
            style="bold cyan",
        ))
        if (
            accum is not None
            and flow_detail.total_net_flow < Decimal("0")
            and has_current_flow_confirmation(accum)
        ):
            flow_group.append(Text(
                "Interpretation: recent signal-window accumulation is occurring inside a negative longer-term flow backdrop.",
                style="dim yellow",
            ))
        elif (
            accum is not None
            and flow_detail.total_net_flow < Decimal("0")
            and accum.foreign_flow_score >= config.watch_min_score
            and not has_current_flow_confirmation(accum)
        ):
            flow_group.append(Text(
                "Interpretation: longer-term flow is negative and the current signal window lacks foreign-flow confirmation.",
                style="dim yellow",
            ))
        elif accum is not None and flow_detail.total_net_flow > Decimal("0") and accum.foreign_flow_score < config.watch_min_score:
            flow_group.append(Text(
                "Interpretation: longer-term net buying exists, but the current signal window is still weak.",
                style="dim yellow",
            ))

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

    # ── Strategy rule evidence (Phase D VO) ──────────────────────────────────
    if include_strategy and strategy_evidence is not None:
        history_group.append(Text(""))
        se = strategy_evidence
        _outcome_style = {
            "MATCHED": "bold green",
            "NOT_MATCHED": "yellow",
            "UNAVAILABLE": "dim",
            "INVALID": "bold red",
        }.get(se.outcome.value, "white")
        outcome_line = Text()
        outcome_line.append(f"Strategy Rule: {se.strategy_name}", style="bold cyan")
        outcome_line.append("  Outcome: ")
        outcome_line.append(se.outcome.value, style=_outcome_style)
        history_group.append(outcome_line)

        mr = se.matched_rule
        if mr is not None:
            rule_table = compact_table(show_header=False)
            rule_table.add_column("Field", style="bold")
            rule_table.add_column("Value")
            if mr.rule_name:
                rule_table.add_row("Rule", mr.rule_name)
            if mr.rule_outcome:
                rule_table.add_row("Rule outcome", mr.rule_outcome)
            if mr.setup_family:
                rule_table.add_row("Setup family", mr.setup_family)
            if mr.setup_phase:
                rule_table.add_row("Setup phase", mr.setup_phase)
            rule_table.add_row("Evidence route", mr.evidence_route)
            history_group.append(rule_table)
            for line in list(mr.rationale)[:3]:
                history_group.append(Text(f"  {line}", style="dim"))

        scores_table = compact_table(show_header=False)
        scores_table.add_column("Metric", style="bold")
        scores_table.add_column("Value")
        if se.coverage_score is not None:
            scores_table.add_row("Coverage", f"{se.coverage_score:.2f}")
        if se.conviction_score is not None:
            scores_table.add_row("Conviction", f"{se.conviction_score:.2f}")
        if se.freshness_score is not None:
            scores_table.add_row("Freshness", f"{se.freshness_score:.2f}")
        if se.coverage_score is not None or se.conviction_score is not None or se.freshness_score is not None:
            history_group.append(scores_table)

        if not mr:
            for line in list(se.rationale)[:3]:
                history_group.append(Text(f"  {line}", style="dim"))
        if se.unavailable_reasons:
            for reason in list(se.unavailable_reasons)[:2]:
                history_group.append(Text(f"  ⚠ {reason}", style="dim yellow"))

        history_group.append(Text(
            "  DIAGNOSTIC — strategy evidence does not control ENTER/WATCH/AVOID",
            style="dim",
        ))

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

            _sentiment_label = Text("News Sentiment (3d): ", style="bold cyan")
            _sentiment_label.append(call_val, style=call_style)
            sentiment_group.append(_sentiment_label)
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
