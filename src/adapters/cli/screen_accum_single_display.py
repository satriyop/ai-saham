"""
Single-window display rendering for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

from src.adapters.cli.effective_session_display import format_effective_session_label
from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.screen_accum_enrichment_display import (
    _evidence_factor_rows,
    _signal_flow_factor_rows,
    build_enrichment_details_table,
)
from src.adapters.cli.screen_accum_formatters import (
    _STRAT_SYMBOL,
    AccumulationDisplayConfig,
    _alignment_text,
    _coverage_text,
    _phase_cell,
    _price_text,
    _readiness_text,
    _risk_detail_line,
    _risk_tier,
    format_disc_pct,
)
from src.adapters.cli.screen_accum_sector_macro_display import build_sector_macro_panel
from src.adapters.shared.decision_display import (
    coverage_pct,
    format_accum_breakdown,
    format_action_why,
    format_market_context_lines,
    format_primary_setup_family,
    format_setup_readiness,
    named_setup_match_glyphs,
    readiness_and_family,
)
from src.adapters.shared.score_display_labels import (
    ACCUM,
    ACCUM_DEFINITION,
    FLOW_GRP,
    FLOW_GRP_DEFINITION,
    FLOW_RATIO_PCT,
    SETUP_GRP,
    SIGNAL,
    SIGNAL_DEFINITION,
)
from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
from src.application.dto.accumulation_screen import (
    AccumulationScreenResponse,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)


def _panel_subtitle(
    *,
    window_days: int,
    screened_at,
    effective_session: EffectiveMarketSession | None,
) -> str:
    base = f"{window_days} sessions / {screened_at}"
    if effective_session is None:
        return base
    return f"{base} · {format_effective_session_label(effective_session)}"


def _build_decision_why_table(candidates: list) -> Any:
    """Per-candidate Action Why — same strings as TUI (decision_display)."""
    table = compact_table()
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Ticker", style="bold", width=6)
    table.add_column("Action", width=14)
    table.add_column("Gate", width=8)
    table.add_column("Why Action")
    for i, c in enumerate(candidates, 1):
        fields = extract_screen_accum_board_fields(c, phase_style="full")
        why = format_action_why(c, gate=fields.gate) or "—"
        table.add_row(str(i), fields.ticker, fields.action, fields.gate, why)
    return table


def _build_accum_breakdown_lines(candidates: list) -> list[Text]:
    """One-line Accum recipe per candidate (shared format_accum_breakdown)."""
    lines: list[Text] = [Text(f"\n{ACCUM} breakdown (same path as TUI)", style="bold cyan")]
    for c in candidates:
        fields = extract_screen_accum_board_fields(c, phase_style="short")
        bd = format_accum_breakdown(c, accum_display=fields.accum)
        lines.append(Text(f"  {fields.ticker}: {bd}", style="dim"))
    return lines


def _build_setup_readiness_lines(candidates: list) -> list[Text]:
    """Setup-phase readiness (not data-freshness Ready column)."""
    lines: list[Text] = [Text("\nSetup readiness (typed; never invent READY)", style="bold cyan")]
    for c in candidates:
        readiness, family = readiness_and_family(c)
        phrase = format_setup_readiness(readiness, setup_family=family, style="full")
        ticker = str(getattr(c, "ticker", "?") or "?")
        lines.append(Text(f"  {ticker}: {phrase}", style="dim"))
    return lines


def _build_judgment_header(candidate: Any) -> Any:
    """Single-ticker judgment strip (ADR-054 S1) — present-only, no re-score.

    Reuses shared board field extraction + action-why formatters so CLI/TUI
    cannot diverge on Action/Gate/Why.
    """
    fields = extract_screen_accum_board_fields(candidate, phase_style="full")
    why = format_action_why(candidate, gate=fields.gate)
    family = format_primary_setup_family(candidate)
    cov = coverage_pct(candidate)
    auth = f"{cov:.0f}%" if cov is not None else "—"

    table = compact_table(show_header=False)
    table.add_column("Key", style="bold cyan", width=12)
    table.add_column("Value")
    table.add_row("Ticker", fields.ticker)
    table.add_row("Action", fields.action)
    table.add_row("Gate", fields.gate)
    table.add_row(SIGNAL, fields.signal)
    table.add_row(ACCUM, fields.accum)
    table.add_row("Authority", auth)
    table.add_row("Phase", fields.phase)
    table.add_row("Family", family)
    table.add_row("Why", why or "—")
    return table


def _build_named_setup_match_table(candidates: list) -> Any:
    """Compact pattern board: primary family + FB/CS/SM/PB match glyphs.

    Diagnostic only — MATCH does not mean ENTER. Glyphs: M MATCH, ~ PARTIAL,
    · NO_MATCH, - not evaluated.
    """
    table = compact_table()
    table.add_column("Ticker", style="bold")
    table.add_column("Primary")
    table.add_column("FB", justify="center")
    table.add_column("CS", justify="center")
    table.add_column("SM", justify="center")
    table.add_column("PB", justify="center")
    table.add_column("Source")
    for c in candidates:
        glyphs = named_setup_match_glyphs(c)
        sfr = getattr(c, "setup_family_result", None)
        source = getattr(sfr, "setup_family_source", None) if sfr is not None else None
        source_s = str(source or "-").replace("detected_screen_evidence", "screen")
        source_s = source_s.replace("fallback_unknown", "unknown")
        source_s = source_s.replace("strategy_evidence", "strategy")
        source_s = source_s.replace("explicit_request", "explicit")
        table.add_row(
            str(getattr(c, "ticker", "?") or "?"),
            format_primary_setup_family(c),
            glyphs.get("FB", "-"),
            glyphs.get("CS", "-"),
            glyphs.get("SM", "-"),
            glyphs.get("PB", "-"),
            source_s,
        )
    return table


def _build_market_context_panel(market_context: Any | None):
    """Diagnostic-only market regime panel (does not move Action)."""
    if market_context is None:
        return None
    body_lines = format_market_context_lines(market_context)
    # Strip Rich markup tags from shared lines for plain CLI Text
    plain = []
    for line in body_lines[1:]:  # skip section header (panel title covers it)
        plain.append(line.replace("[#9b8fb8]", "").replace("[/]", "").replace("[dim]", ""))
    if not plain:
        plain = ["not evaluated for this screen run"]
    content = Text(
        "\n".join(plain)
        + "\n\nDiagnostic only — not applied to DecisionPolicy / Action on screen accum.",
        style="dim",
    )
    return panel(content, title="Market context (diagnostic)")


def _format_market_context_meta(market_context: Any | None) -> str:
    if market_context is None:
        return "not evaluated for this screen run · diagnostic only (does not move Action)"
    regime = getattr(market_context, "regime", None)
    regime_s = str(getattr(regime, "value", regime) or regime or "—")
    conv = getattr(market_context, "conviction", None)
    conv_s = f" conviction {float(conv):.2f}" if isinstance(conv, (int, float)) else ""
    return f"{regime_s}{conv_s} · diagnostic only (does not move Action)"


def _scoring_definitions_panel(display_config: AccumulationDisplayConfig):
    p = display_config.accum_score_policy

    accum_table = compact_table()
    accum_table.add_column("Factor", style="bold")
    accum_table.add_column("Max", justify="right")
    accum_table.add_column("Mechanism")
    accum_table.add_row(
        "Net days",
        f"{p.consistency.weight:g}",
        "net_buy_days / total_days × max points",
    )
    accum_table.add_row(
        "Streak",
        f"{p.streak.weight:g}",
        f"exponential saturation: max × (1 - exp(-streak / {p.streak.tau_days:g}))",
    )
    accum_table.add_row(
        "F_VWAP%",
        f"{p.vwap_discount.weight:g}",
        f"linear 0-{p.vwap_discount.saturate_at:g}% underwater; capped at max",
    )
    accum_table.add_row(
        "RSI",
        f"{p.rsi_headroom.weight:g}",
        (
            f"tent score: 0 at <= {p.rsi_headroom.low:g} or >= {p.rsi_headroom.high:g}; "
            f"peak at {p.rsi_headroom.peak:g}"
        ),
    )
    accum_table.add_row(
        FLOW_RATIO_PCT,
        f"{p.foreign_flow_ratio.weight:g}",
        f"net foreign turnover share; linear to {p.foreign_flow_ratio.saturate_at:g}% "
        f"(Accum component only — not {ACCUM} total, not {FLOW_GRP})",
    )
    _bb_scored = p.bb_squeeze.enabled
    accum_table.add_row(
        "BB%ile",
        f"{p.bb_squeeze.weight:g}" if _bb_scored else "—",
        (
            f"squeeze score: best below {p.bb_squeeze.tight_pctile:.0%}; "
            f"fades to 0 by {p.bb_squeeze.loose_pctile:.0%}"
            if _bb_scored
            else (
                "structure/setup evidence (shown diagnostically); not scored in default flow score"
            )
        ),
    )
    accum_table.add_row(
        "BCI",
        f"{p.bci.cluster_points:g}",
        (
            f"Tier-1 broker concentration: CLUSTER {p.bci.cluster_points:g}, "
            f"STABLE {p.bci.stable_points:g}"
        ),
    )

    signal_table = compact_table(show_header=False)
    signal_table.add_column("Key", style="bold cyan")
    signal_table.add_column("Definition")
    signal_table.add_row(SIGNAL, SIGNAL_DEFINITION)
    signal_table.add_row(
        f"{SETUP_GRP} / {FLOW_GRP}",
        (
            f"{SETUP_GRP} = setup-quality group (0–100). "
            f"{FLOW_GRP} = flow-confirmation group (0–100). "
            f"Neither is {ACCUM}. Conf% = evidence coverage. "
            "Flags = do-no-harm penalties (VAL/ANL/INS)."
        ),
    )
    signal_table.add_row(
        "Signal status",
        (
            "STRONG / MODERATE / WEAK from score thresholds; "
            "entry quality maps to ENTER / WATCH / AVOID."
        ),
    )
    signal_table.add_row(
        "Risk status",
        (
            "RiskEngine gate state, not a score: OPEN means no structural/execution "
            "gate fired; BLOCKED means a risk gate fired."
        ),
    )

    return panel(
        Group(
            Text(f"{ACCUM} score components (foreign accumulation)", style="bold cyan"),
            Text(ACCUM_DEFINITION, style="dim"),
            accum_table,
            Text(f"\n{SIGNAL} / risk definitions", style="bold cyan"),
            Text(SIGNAL_DEFINITION, style="dim"),
            Text(FLOW_GRP_DEFINITION, style="dim"),
            signal_table,
        ),
        title="Scoring Definitions (ADR-043)",
    )


def display_results(
    response: AccumulationScreenResponse,
    candidates: list,
    universe_label: str,
    show_top_broker: bool,
    display_config: AccumulationDisplayConfig,
    include_detail: bool = False,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
    effective_session: EffectiveMarketSession | None = None,
    market_context: Any | None = None,
    deep_evidence_by_ticker: dict | None = None,
    deep_flags: Any | None = None,
) -> None:
    """Render accumulation screener results as terminal table.

    `candidates` is the already-filtered/limited projection from
    src.application.services.screen_accum_result_projector — this function
    must not independently filter, sort, or slice `response.candidates`.

    ``market_context`` is display-only (diagnostic). It must not imply
    DecisionPolicy used regime on this screen run (B-MCE-policy is separate).
    """
    show_context_ticker = len(candidates) > 1

    if not candidates:
        empty = compact_table(show_header=False)
        empty.add_column("Message")
        empty.add_row("No candidates found matching the criteria.")
        empty.add_row(
            f"Checked {response.total_tickers_checked} tickers; "
            f"skipped {response.tickers_skipped} with insufficient data."
        )
        empty.add_row(f"Next: saham fetch market --universe {universe_label}")
        console().print(
            panel(
                empty,
                title=f"Foreign Accumulation - {universe_label.upper()}",
                subtitle=_panel_subtitle(
                    window_days=response.window_days,
                    screened_at=response.screened_at,
                    effective_session=effective_session,
                ),
            )
        )
        return

    action_table = compact_table()
    action_table.add_column("Action")
    action_table.add_column("#", justify="right")
    action_table.add_column("Ticker", style="bold")
    action_table.add_column("Disc%", justify="right")
    action_table.add_column("Price", justify="right")
    action_table.add_column(SIGNAL, justify="right")
    action_table.add_column(ACCUM, justify="right")
    action_table.add_column("Gate")
    action_table.add_column("Trend")
    action_table.add_column("Phase")
    if strategy_signals is not None:
        action_table.add_column("Strat")

    evidence_table = compact_table()
    evidence_table.add_column("Pts", justify="right")
    if show_context_ticker:
        evidence_table.add_column("Ticker", style="bold")
    evidence_table.add_column("Factor")
    evidence_table.add_column("Value", justify="right")
    evidence_table.add_column("Means")

    signal_table = compact_table()
    signal_table.add_column("Strength")
    if show_context_ticker:
        signal_table.add_column("Ticker", style="bold")
    signal_table.add_column(SIGNAL, justify="right")
    signal_table.add_column(SETUP_GRP, justify="right")
    signal_table.add_column(FLOW_GRP, justify="right")
    signal_table.add_column("Conf%", justify="right")
    signal_table.add_column("Max")
    signal_table.add_column("Flags")

    # Accum-style factor dump for FlowGrp (Option 1: always-on second panel).
    flow_grp_table = compact_table()
    flow_grp_table.add_column("Pts", justify="right")
    if show_context_ticker:
        flow_grp_table.add_column("Ticker", style="bold")
    flow_grp_table.add_column("Factor")
    flow_grp_table.add_column("Value", justify="right")
    flow_grp_table.add_column("Means")

    risk_table = compact_table()
    risk_table.add_column("Status")
    if show_context_ticker:
        risk_table.add_column("Ticker", style="bold")
    risk_table.add_column("Tier")
    risk_table.add_column("Gate")

    data_table = compact_table()
    data_table.add_column("Align")
    data_table.add_column("Ready")
    if show_context_ticker:
        data_table.add_column("Ticker", style="bold")
    data_table.add_column("Candle")
    data_table.add_column("Broker")
    data_table.add_column("Coverage")
    data_table.add_column("Missing")

    risk_detail_lines: list[Text] = []

    for i, c in enumerate(candidates, 1):
        # Color flow score
        if c.accum_score >= display_config.enter_min_accum_score:
            score_style = "green"
        elif c.accum_score >= display_config.watch_min_accum_score:
            score_style = "yellow"
        else:
            score_style = ""

        # Signal assessment cell
        if c.signal_assessment is not None:
            sa = c.signal_assessment.assessment
            cs = sa.score
            if cs >= 70:
                cmp_style = "bold green"
            elif cs >= 55:
                cmp_style = "green"
            elif cs >= 45:
                cmp_style = "yellow"
            else:
                cmp_style = "red"
            cmp_cell = Text(sa.score_label, style=cmp_style)
        else:
            cmp_cell = Text("—", style="bright_black")

        gate_triggered = (
            c.risk_assessment.gate_triggered
            if c.risk_assessment and c.risk_assessment.gate_triggered
            else None
        )
        gate_status = "BLOCKED" if gate_triggered else ("OPEN" if c.risk_assessment else "N/A")
        gate_style = (
            "bold red" if gate_triggered else ("green" if c.risk_assessment else "bright_black")
        )
        gate_cell = Text(gate_status, style=gate_style)

        if c.trade_setup is not None:
            _action_style = {
                "ENTER": "bold green",
                "WATCH": "yellow",
                "AVOID": "red",
                "BLOCKED_EXECUTION": "bold red",
                "BLOCKED_STRUCTURAL": "bold red",
            }.get(c.trade_setup.action.value, "white")
            action_cell = Text(c.trade_setup.action.short, style=_action_style)
        else:
            action_cell = Text("—", style="bright_black")

        row = [
            action_cell,
            str(i),
            c.ticker,
            format_disc_pct(c.vwap_discount_pct),
            _price_text(c.current_price),
            cmp_cell,
            Text(f"{c.accum_score:.1f}", style=score_style),
            gate_cell,
            c.trend,
            _phase_cell(c.setup_phase),
        ]
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            strat_style = (
                "green" if raw == "LOW_RISK" else ("red" if raw == "HIGH_RISK" else "bright_black")
            )
            row.append(Text(sym, style=strat_style))
        action_table.add_row(*row)

        for evidence_row in _evidence_factor_rows(c, display_config):
            if show_context_ticker:
                evidence_table.add_row(evidence_row[0], c.ticker, *evidence_row[1:])
            else:
                evidence_table.add_row(*evidence_row)

        if c.signal_assessment is not None:
            sa = c.signal_assessment.assessment
            bd = sa.breakdown_dict
            _setup = bd.get("setup_quality_group")
            _flow = bd.get("flow_confirmation_group")
            _conf = bd.get("signal_authority_coverage")
            _flags = getattr(c.signal_assessment, "active_flags", ())
            _constraints = getattr(sa, "decision_constraints", None)
            _flag_abbr = {
                "VALUATION_STRETCHED": "VAL",
                "ANALYST_BEARISH": "ANL",
                "INSIDER_SELLING": "INS",
            }
            signal_row = [
                sa.strength.value,
                str(sa.score),
                f"{_setup:.0f}" if _setup is not None else "-",
                f"{_flow:.0f}" if _flow is not None else "-",
                f"{_conf:.0f}%" if _conf is not None else "-",
                _constraints.max_decision if _constraints is not None else "-",
                " ".join(_flag_abbr.get(f, f[:3]) for f in _flags) or "-",
            ]
            if show_context_ticker:
                signal_table.add_row(signal_row[0], c.ticker, *signal_row[1:])
            else:
                signal_table.add_row(*signal_row)
        else:
            signal_row = ["-", "-", "-", "-", "-", "-", "-"]
            if show_context_ticker:
                signal_table.add_row(signal_row[0], c.ticker, *signal_row[1:])
            else:
                signal_table.add_row(*signal_row)

        for flow_row in _signal_flow_factor_rows(c):
            if show_context_ticker:
                flow_grp_table.add_row(flow_row[0], c.ticker, *flow_row[1:])
            else:
                flow_grp_table.add_row(*flow_row)

        risk_row = [
            gate_status,
            _risk_tier(c.risk_assessment),
            gate_triggered or "-",
        ]
        if show_context_ticker:
            risk_table.add_row(risk_row[0], c.ticker, *risk_row[1:])
        else:
            risk_table.add_row(*risk_row)
        risk_detail_lines.append(_risk_detail_line(i, c))

        missing = [
            label
            for label, val in [
                ("seasonal", c.seasonal_edge),
                ("analyst", c.analyst_consensus),
                ("holding", c.shareholding),
                ("bandar", c.bandar_detector),
                ("fundam", c.fundamentals),
                ("fwd_eps", c.forward_estimates),
            ]
            if val is None
        ]
        data_row = [
            _alignment_text(c),
            _readiness_text(c),
            c.latest_candle_date.isoformat() if c.latest_candle_date else "-",
            c.latest_broker_date.isoformat() if c.latest_broker_date else "-",
            _coverage_text(c),
            " ".join(missing) if missing else "-",
        ]
        if show_context_ticker:
            data_table.add_row(data_row[0], data_row[1], c.ticker, *data_row[2:])
        else:
            data_table.add_row(*data_row)

    details_table, has_detail_rows = build_enrichment_details_table(
        candidates,
        show_context_ticker,
        show_top_broker,
    )

    decision_table = _build_decision_why_table(candidates)
    named_setup_table = _build_named_setup_match_table(candidates)
    accum_breakdown_lines = _build_accum_breakdown_lines(candidates)
    setup_readiness_lines = _build_setup_readiness_lines(candidates)

    # ADR-054 S1: single-candidate case file opens with a judgment strip.
    judgment_single = len(candidates) == 1
    sections: list[Any] = []
    if judgment_single:
        sections.append(
            panel(
                Group(
                    _build_judgment_header(candidates[0]),
                    Text(
                        "\nJudgment case file (ADR-054). Action is composed "
                        f"TradeSetup when signal+risk present. Structure "
                        f"(horizon/SL/TP/lots): saham plan swing "
                        f"{getattr(candidates[0], 'ticker', 'TICKER')}.",
                        style="dim",
                    ),
                ),
                title="Judgment",
            )
        )

    sections.extend(
        [
            panel(
                Group(
                    action_table,
                    Text(
                        "\nPhase is accumulation-lifecycle diagnostic. Pattern match "
                        "board is diagnostic (MATCH ≠ ENTER). "
                        "Deep judgment: saham screen accum TICKER. "
                        "Trade structure (horizon/SL/TP): saham plan swing TICKER.",
                        style="dim",
                    ),
                ),
                title="Candidate Actions",
            ),
            panel(
                Group(
                    named_setup_table,
                    Text(
                        "\nFB=foreign-bounce  CS=coiled-spring  SM=smart-money  "
                        "PB=pullback-continuation\n"
                        "M=MATCH  ~=PARTIAL  ·=NO_MATCH  -=not evaluated. "
                        "Primary family from resolver; does not grant entry.",
                        style="dim",
                    ),
                ),
                title="Setup pattern match (diagnostic)",
            ),
            panel(
                Group(
                    decision_table,
                    Text(
                        "\nWhy Action uses the same shared formatters as TUI focus/Enter "
                        "(authority, setup readiness, constraints, gate). "
                        "Does not re-score.",
                        style="dim",
                    ),
                ),
                title="Decision · Action Why",
            ),
            panel(
                Group(
                    evidence_table,
                    *accum_breakdown_lines,
                ),
                title=f"{ACCUM} score components",
            ),
            panel(
                Group(
                    signal_table,
                    *setup_readiness_lines,
                ),
                title=f"{SIGNAL} summary (SignalEngine — not {ACCUM})",
            ),
            panel(
                Group(
                    flow_grp_table,
                    Text(
                        f"\n{FLOW_GRP} detail mirrors Accum factors "
                        f"(Pts/Factor/Value/Means). "
                        "RSI/BB are not in FlowGrp. Bandar blends when present; "
                        "group_cap ceilings correlated broker evidence.",
                        style="dim",
                    ),
                ),
                title=f"{SIGNAL} · {FLOW_GRP} components",
            ),
            panel(
                Group(
                    risk_table,
                    Text("\nGate detail", style="bold cyan"),
                    *risk_detail_lines,
                    Text(
                        "\nRiskEngine is gate-based: OPEN means no "
                        "structural/execution risk gate fired; "
                        "BLOCKED means a gate stopped or downgraded action.",
                        style="dim",
                    ),
                    Text(
                        "\nTechnicalGate is not evaluated by screen accum "
                        "(execution microstructure). Judgment Action above "
                        "already includes structural/execution gates that fired.",
                        style="dim",
                    ),
                ),
                title="Risk Status",
            ),
            panel(data_table, title="Data Coverage"),
        ]
    )
    mce_panel = _build_market_context_panel(market_context)
    if mce_panel is not None:
        sections.append(mce_panel)
    # ADR-054: sector-macro lives on single-ticker judgment, not plan swing.
    if judgment_single:
        smc_panel = build_sector_macro_panel(
            getattr(candidates[0], "sector_macro_context_evidence", None)
        )
        if smc_panel is not None:
            sections.append(smc_panel)
    if has_detail_rows:
        sections.append(panel(details_table, title="Enrichment Details"))

    console().print(
        panel(
            Group(*sections),
            title=f"Foreign Accumulation - {universe_label.upper()}",
            subtitle=_panel_subtitle(
                window_days=response.window_days,
                screened_at=response.screened_at,
                effective_session=effective_session,
            ),
        )
    )

    # ADR-054 S1 complete: optional analysis evidence (never Action / structure).
    if deep_evidence_by_ticker:
        from src.adapters.cli.screen_accum_deep_evidence_display import (
            print_screen_deep_evidence_panels,
        )

        print_screen_deep_evidence_panels(
            deep_evidence_by_ticker=deep_evidence_by_ticker,
            deep_flags=deep_flags,
            candidates=candidates,
        )

    if not include_detail:
        return

    # Render run context cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    if effective_session is not None:
        meta_table.add_row(
            "Effective session",
            format_effective_session_label(effective_session),
        )

    meta_table.add_row(
        "Market context",
        _format_market_context_meta(market_context),
    )

    meta_table.add_row(
        "Stats",
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}",
    )

    if response.provider == "stockbit":
        meta_table.add_row(
            "Provider",
            (
                "stockbit  ·  foreign aggregate from IDX  ·  "
                "broker detail: inst desk proxy (10 codes, not all-foreign)"
            ),
        )
    else:
        meta_table.add_row(
            "Provider",
            f"{response.provider} (aggregate foreign flow)\n"
            "For per-broker detail: run `saham fetch stockbit login`, "
            "then fetch with `--provider stockbit`",
        )

    explain_lines = [
        "Candidate Actions is the screen summary. Context panels explain why.",
        (
            "Decision · Action Why matches TUI (shared decision_display). "
            "Market context on this screen is diagnostic only — it does not "
            "move Action until an explicit B-MCE-policy change."
        ),
        (
            f"{ACCUM} = foreign-accumulation composite (0–100). "
            f"{SIGNAL} = SignalEngine total (0–100). Different engines — "
            "they can disagree without either being 'wrong'."
        ),
        (
            f"{SETUP_GRP}/{FLOW_GRP} live only under {SIGNAL} (group contributions). "
            f"{FLOW_RATIO_PCT} is an Accum component (turnover share), not {FLOW_GRP}."
        ),
        (
            "GATE OPEN means no structural/execution risk gate fired; "
            "it does not mean the ticker is risk-free."
        ),
        (
            f"{FLOW_RATIO_PCT} = avg net foreign % of turnover. "
            "F_VWAP%/Disc% positive = price below foreign average buy cost. "
            "BB%ILE lower = tighter squeeze."
        ),
    ]
    if strategy_signals is not None:
        explain_lines.append(
            f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )

    meta_table.add_row("Definitions", "\n".join(explain_lines))
    meta_table.add_row(
        "Disclaimer",
        "Swing trade watchlist — cross-check with `saham screen pre-open` "
        "for intraday entry timing.\n"
        "DISCLAIMER: Analysis only, not trading advice.",
    )

    console().print(
        panel(
            meta_table,
            title="Run Context",
        )
    )
    console().print(_scoring_definitions_panel(display_config))
