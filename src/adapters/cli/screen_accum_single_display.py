"""
Single-window display rendering for accumulation screen CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.screen_accum_enrichment_display import (
    _evidence_factor_rows,
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
from src.application.dto.accumulation_screen import (
    AccumulationScreenResponse,
)


def _scoring_definitions_panel(display_config: AccumulationDisplayConfig):
    p = display_config.foreign_flow_score_policy

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
        "Flow%",
        f"{p.foreign_flow_ratio.weight:g}",
        f"net foreign turnover share; linear to {p.foreign_flow_ratio.saturate_at:g}%",
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
                "structure/setup evidence (shown diagnostically); "
                "not scored in default flow score"
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
    signal_table.add_row(
        "Signal score",
        (
            "SignalEngine attractiveness score (0-100). "
            "Setup = setup-quality group (0-100). "
            "Flow = flow-confirmation group (0-100). "
            "Conf% = evidence confidence (how much weight is covered). "
            "Flags = active do-no-harm penalties (VAL/ANL/INS)."
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
            Text("Foreign-flow score components", style="bold cyan"),
            accum_table,
            Text("\nSignal / risk definitions", style="bold cyan"),
            signal_table,
        ),
        title="Scoring Definitions",
    )


def display_results(
    response: AccumulationScreenResponse,
    candidates: list,
    universe_label: str,
    show_top_broker: bool,
    display_config: AccumulationDisplayConfig,
    include_explanation: bool = False,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    """Render accumulation screener results as terminal table.

    `candidates` is the already-filtered/limited projection from
    src.application.services.screen_accum_result_projector — this function
    must not independently filter, sort, or slice `response.candidates`.
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
                subtitle=f"{response.window_days} sessions / {response.screened_at}",
            )
        )
        return

    action_table = compact_table()
    action_table.add_column("Action")
    action_table.add_column("#", justify="right")
    action_table.add_column("Ticker", style="bold")
    action_table.add_column("Disc%", justify="right")
    action_table.add_column("Price", justify="right")
    action_table.add_column("Signal", justify="right")
    action_table.add_column("Accum", justify="right")
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
    signal_table.add_column("Signal")
    if show_context_ticker:
        signal_table.add_column("Ticker", style="bold")
    signal_table.add_column("Score", justify="right")
    signal_table.add_column("Setup", justify="right")
    signal_table.add_column("Flow", justify="right")
    signal_table.add_column("Conf%", justify="right")
    signal_table.add_column("Max")
    signal_table.add_column("Flags")

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
        if c.foreign_flow_score >= display_config.enter_min_foreign_flow_score:
            score_style = "green"
        elif c.foreign_flow_score >= display_config.watch_min_foreign_flow_score:
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
        gate_status = "BLOCKED" if gate_triggered else (
            "OPEN" if c.risk_assessment else "N/A"
        )
        gate_style = "bold red" if gate_triggered else (
            "green" if c.risk_assessment else "bright_black"
        )
        gate_cell = Text(gate_status, style=gate_style)

        if c.trade_setup is not None:
            _action_style = {
                "ENTER":              "bold green",
                "WATCH":              "yellow",
                "AVOID":              "red",
                "BLOCKED_EXECUTION":  "bold red",
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
            Text(f"{c.foreign_flow_score:.1f}", style=score_style),
            gate_cell,
            c.trend,
            _phase_cell(c.setup_phase),
        ]
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            strat_style = "green" if raw == "LOW_RISK" else (
                "red" if raw == "HIGH_RISK" else "bright_black"
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
            label for label, val in [
                ("seasonal",  c.seasonal_edge),
                ("analyst",   c.analyst_consensus),
                ("holding",   c.shareholding),
                ("bandar",    c.bandar_detector),
                ("fundam",    c.fundamentals),
                ("fwd_eps",   c.forward_estimates),
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

    sections = [
        panel(
            Group(
                action_table,
                Text(
                    "\nPhase is accumulation-lifecycle diagnostic; use "
                    "saham analyze swing TICKER --setup SETUP for setup gates "
                    "and entry validation.",
                    style="dim",
                ),
            ),
            title="Candidate Actions",
        ),
        panel(evidence_table, title="Foreign Flow Score"),
        panel(signal_table, title="Signal"),
        panel(
            Group(
                risk_table,
                Text("\nWhy", style="bold cyan"),
                *risk_detail_lines,
                Text(
                    "\nRiskEngine is gate-based: OPEN means no structural/execution "
                    "risk gate fired; "
                    "BLOCKED means a gate stopped or downgraded action.",
                    style="dim",
                ),
                Text(
                    "\nTechnicalGate is not evaluated by screen accum. Use "
                    "saham analyze swing TICKER --with-technical-gate for "
                    "technical execution-gate diagnostics.",
                    style="dim",
                ),
            ),
            title="Risk Status",
        ),
        panel(data_table, title="Data Coverage"),
    ]
    if has_detail_rows:
        sections.append(panel(details_table, title="Enrichment Details"))

    console().print(
        panel(
            Group(*sections),
            title=f"Foreign Accumulation - {universe_label.upper()}",
            subtitle=f"{response.window_days} sessions / {response.screened_at}",
        )
    )

    if not include_explanation:
        return

    # Render run context cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    meta_table.add_row(
        "Stats",
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )

    if response.provider == "stockbit":
        meta_table.add_row(
            "Provider",
            (
                "stockbit  ·  foreign aggregate from IDX  ·  "
                "broker detail: inst desk proxy (10 codes, not all-foreign)"
            )
        )
    else:
        meta_table.add_row(
            "Provider",
            f"{response.provider} (aggregate foreign flow)\n"
            "For per-broker detail: run `saham fetch stockbit login`, "
            "then fetch with `--provider stockbit`"
        )

    explain_lines = [
        "Candidate Actions is the screen summary. Context panels explain why.",
        (
            "ACCUM is deterministic foreign-flow evidence (0-100). "
            "SIGNAL is SignalEngine attractiveness (0-100)."
        ),
        (
            "GATE OPEN means no structural/execution risk gate fired; "
            "it does not mean the ticker is risk-free."
        ),
        (
            "FLOW% = avg net foreign % of turnover. "
            "F_VWAP% positive = price below foreign average buy cost. "
            "BB%ILE lower = tighter squeeze."
        ),
    ]
    if strategy_signals is not None:
        explain_lines.append(
            f"STRAT ({strategy_name}): "
            "↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )

    meta_table.add_row("Definitions", "\n".join(explain_lines))
    meta_table.add_row(
        "Disclaimer",
        "Swing trade watchlist — cross-check with `saham screen pre-open` "
        "for intraday entry timing.\n"
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Run Context",
        )
    )
    console().print(_scoring_definitions_panel(display_config))
