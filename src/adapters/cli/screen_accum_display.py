"""
Display helpers for accumulation CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.domain.services.trading_calendar import trading_sessions_apart
from src.infrastructure.config.swing_config import (
    load_swing_config as _load_swing_config,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config as _load_accumulation_screener_config,
)

_SC = _load_swing_config()
_ASC = _load_accumulation_screener_config()
_TABLE_WIDTH = 93


def format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def fmt_score(s: float | None) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= _ASC.display.enter_min_foreign_flow_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= _ASC.display.watch_min_foreign_flow_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = _ASC.display.coiled_spring_min_foreign_flow_score
    hot = [w for w in windows if candidates_by_window.get(w) and candidates_by_window[w].foreign_flow_score >= threshold]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if c and c.foreign_flow_score >= threshold and c.bb_width_pctile is not None and c.bb_width_pctile <= _ASC.display.coiled_spring_bb_pctile:
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"


def notation_label(snapshot) -> str:
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


def notation_detail(snapshot) -> str:
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


_STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}


def _price_text(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def _risk_reason(assessment) -> str:
    if assessment is None or not assessment.rationale:
        return "-"
    return "; ".join(assessment.rationale)


def _risk_tier(assessment) -> str:
    if assessment is None or not assessment.gate_triggered:
        return "-"
    return "structural" if assessment.gate_is_structural else "execution"


def _risk_detail_line(rank: int, candidate: AccumulationCandidate) -> Text:
    assessment = candidate.risk_assessment
    if assessment is None:
        return Text(f"#{rank} {candidate.ticker}: risk unavailable", style="dim")
    if not assessment.gate_triggered:
        return Text(f"#{rank} {candidate.ticker}: no risk gate fired", style="dim")
    reason = _risk_reason(assessment)
    return Text(
        f"#{rank} {candidate.ticker}: {assessment.gate_triggered} - {reason}",
        style="red" if assessment.gate_is_structural else "yellow",
    )


def _data_freshness(candidate: AccumulationCandidate) -> str:
    if candidate.latest_candle_date is None or candidate.latest_broker_date is None:
        return "MISSING"
    if candidate.latest_candle_date == candidate.latest_broker_date:
        return "OK"
    return "LAG"


def _scoring_definitions_panel():
    p = _ASC.foreign_flow_score_policy

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
        f"tent score: 0 at <= {p.rsi_headroom.low:g} or >= {p.rsi_headroom.high:g}; peak at {p.rsi_headroom.peak:g}",
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
            f"squeeze score: best below {p.bb_squeeze.tight_pctile:.0%}; fades to 0 by {p.bb_squeeze.loose_pctile:.0%}"
            if _bb_scored
            else "structure/setup evidence (shown diagnostically); not scored in default flow score"
        ),
    )
    accum_table.add_row(
        "BCI",
        f"{p.bci.cluster_points:g}",
        f"Tier-1 broker concentration: CLUSTER {p.bci.cluster_points:g}, STABLE {p.bci.stable_points:g}",
    )

    signal_table = compact_table(show_header=False)
    signal_table.add_column("Key", style="bold cyan")
    signal_table.add_column("Definition")
    signal_table.add_row(
        "Signal score",
        "SignalEngine attractiveness score (0-100) from bandar, foreign quality, insider activity, seasonality, analyst, and forward valuation.",
    )
    signal_table.add_row(
        "Signal status",
        "STRONG / MODERATE / WEAK from score thresholds; entry quality maps to ENTER / WATCH / AVOID.",
    )
    signal_table.add_row(
        "Risk status",
        "RiskEngine gate state, not a score: OPEN means no structural/execution gate fired; BLOCKED means a risk gate fired.",
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


def _detail_status(style_key: str) -> Text:
    styles = {
        "GOOD": "green",
        "WARN": "yellow",
        "BAD": "red",
        "INFO": "bright_black",
        "BUY": "cyan",
        "TAILWIND": "green",
        "HEADWIND": "red",
        "BULLISH": "green",
        "BEARISH": "red",
        "ACCUM": "green",
        "DISTRIB": "red",
        "QUALITY": "green",
        "WEAK": "yellow",
        "LAG": "yellow",
    }
    return Text(style_key, style=styles.get(style_key, ""))


def _add_detail_row(table, show_ticker: bool, ticker: str, kind: str, status: str, detail: str) -> None:
    row = [kind]
    if show_ticker:
        row.append(ticker)
    row.extend([_detail_status(status), detail])
    table.add_row(*row)


def _evidence_factor_rows(candidate: AccumulationCandidate) -> list[tuple[str, ...]]:
    bd = (
        candidate.foreign_flow_score_breakdown.breakdown_dict
        if candidate.foreign_flow_score_breakdown else {}
    )
    rsi = f"{candidate.rsi:.1f}" if candidate.rsi is not None else "-"
    flow = f"{candidate.avg_flow_ratio:+.1f}%" if candidate.avg_flow_ratio is not None else "-"
    vwap = (
        f"{candidate.vwap_discount_pct:+.1f}%"
        if candidate.vwap_discount_pct is not None else "-"
    )
    bb = (
        f"{candidate.bb_width_pctile * 100:.0f}%"
        if candidate.bb_width_pctile is not None else "-"
    )
    return [
        (
            f"{bd.get('cons', 0):.1f}",
            "Net days",
            f"{candidate.net_buy_days}/{candidate.total_days}",
            "Foreign buy consistency",
        ),
        (
            f"{bd.get('streak', 0):.1f}",
            "Streak",
            f"{candidate.consecutive_streak}s",
            "Current buy run",
        ),
        (
            f"{bd.get('vwap', 0):.1f}",
            "F_VWAP%",
            vwap,
            "Foreign avg cost vs price",
        ),
        (
            f"{bd.get('rsi', 0):.1f}",
            "RSI",
            rsi,
            "Entry headroom",
        ),
        (
            f"{bd.get('flow', 0):.1f}",
            "Flow%",
            flow,
            "Foreign share of turnover",
        ),
        (
            f"{bd.get('bb', 0):.1f}",
            "BB%ile",
            bb,
            "Volatility squeeze",
        ),
        (
            f"{bd.get('inst', 0):.1f}",
            "BCI",
            candidate.bci_label or "-",
            "Tier-1 broker concentration",
        ),
    ]


def display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    show_top_broker: bool,
    vwap_only: bool,
    squeeze_only: bool,
    include_explanation: bool = False,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    """Render accumulation screener results as terminal table."""
    candidates = response.candidates
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]
    if squeeze_only:
        candidates = [c for c in candidates if c.bb_width_pctile is not None and c.bb_width_pctile <= _ASC.display.coiled_spring_bb_pctile]

    candidates = candidates[:top_n]
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
    action_table.add_column("Price", justify="right")
    action_table.add_column("Signal", justify="right")
    action_table.add_column("Accum", justify="right")
    action_table.add_column("Gate")
    action_table.add_column("Trend")
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
    signal_table.add_column("Bandar", justify="right")
    signal_table.add_column("Foreign", justify="right")
    signal_table.add_column("Insider", justify="right")
    signal_table.add_column("Season", justify="right")
    signal_table.add_column("Analyst", justify="right")
    signal_table.add_column("Fwd", justify="right")

    risk_table = compact_table()
    risk_table.add_column("Status")
    if show_context_ticker:
        risk_table.add_column("Ticker", style="bold")
    risk_table.add_column("Tier")
    risk_table.add_column("Gate")

    data_table = compact_table()
    data_table.add_column("Fresh")
    if show_context_ticker:
        data_table.add_column("Ticker", style="bold")
    data_table.add_column("Candle")
    data_table.add_column("Broker")
    data_table.add_column("Missing")

    details_table = compact_table()
    details_table.add_column("Type")
    if show_context_ticker:
        details_table.add_column("Ticker", style="bold")
    details_table.add_column("Status")
    details_table.add_column("Detail")
    has_detail_rows = False
    risk_detail_lines: list[Text] = []

    for i, c in enumerate(candidates, 1):
        if c.bb_width_pctile is not None:
            pct_int = int(c.bb_width_pctile * 100)
            bb_style = "green" if c.bb_width_pctile <= _SC.coiled_spring_bb_pctile else (
                "yellow" if c.bb_width_pctile <= 0.40 else ""
            )
        # Color flow score
        if c.foreign_flow_score >= _ASC.display.enter_min_foreign_flow_score:
            score_style = "green"
        elif c.foreign_flow_score >= _ASC.display.watch_min_foreign_flow_score:
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
        gate_style = "bold red" if gate_triggered else ("green" if c.risk_assessment else "bright_black")
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
            _price_text(c.current_price),
            cmp_cell,
            Text(f"{c.foreign_flow_score:.1f}", style=score_style),
            gate_cell,
            c.trend,
        ]
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            strat_style = "green" if raw == "LOW_RISK" else ("red" if raw == "HIGH_RISK" else "bright_black")
            row.append(Text(sym, style=strat_style))
        action_table.add_row(*row)

        for evidence_row in _evidence_factor_rows(c):
            if show_context_ticker:
                evidence_table.add_row(evidence_row[0], c.ticker, *evidence_row[1:])
            else:
                evidence_table.add_row(*evidence_row)

        if c.signal_assessment is not None:
            sa = c.signal_assessment.assessment
            bd = sa.breakdown_dict
            signal_row = [
                sa.strength.value,
                str(sa.score),
                f"{bd.get('bandar_intensity', 0):.0f}",
                f"{bd.get('foreign_flow_quality', 0):.0f}",
                f"{bd.get('insider_activity', 0):.0f}",
                f"{bd.get('seasonality_edge', 0):.0f}",
                f"{bd.get('analyst_consensus', 0):.0f}",
                f"{bd.get('forward_valuation', 0):.0f}",
            ]
            if show_context_ticker:
                signal_table.add_row(signal_row[0], c.ticker, *signal_row[1:])
            else:
                signal_table.add_row(*signal_row)
        else:
            signal_row = ["-", "-", "-", "-", "-", "-", "-", "-"]
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

        notation_text = notation_detail(c.ticker_notation)
        if notation_text:
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Notation",
                "WARN" if c.ticker_notation and c.ticker_notation.has_warning else "INFO",
                notation_text,
            )
            has_detail_rows = True

        if c.seasonal_edge is not None:
            se = c.seasonal_edge
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Seasonal",
                "TAILWIND" if se.is_tailwind else ("HEADWIND" if se.is_headwind else "INFO"),
                f"{se.label} (score {se.score:+.2f})",
            )
            has_detail_rows = True

        if c.dividend_risk:
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Corp Act", "WARN", "Dividend risk inside hold window")
            has_detail_rows = True
        if c.rights_issue_risk:
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Corp Act", "WARN", "Rights issue inside hold window")
            has_detail_rows = True
        if c.insider_buying:
            for label in c.recent_insider_buys:
                _add_detail_row(details_table, show_context_ticker, c.ticker, "Insider", "BUY", label)
                has_detail_rows = True

        if c.analyst_consensus is not None:
            ac = c.analyst_consensus
            if ac.is_bullish and (ac.upside_pct or 0) >= 10:
                ac_status = "BULLISH"
            elif ac.sell_count > ac.buy_count:
                ac_status = "BEARISH"
            else:
                ac_status = "INFO"
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Analyst", ac_status, ac.label)
            has_detail_rows = True

        if c.shareholding is not None:
            sh = c.shareholding
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Holding",
                "GOOD" if sh.institution_pct >= 30.0 else "INFO",
                sh.label,
            )
            has_detail_rows = True

        if c.bandar_detector is not None:
            bd = c.bandar_detector
            if bd.accumulation_score >= 4:
                bd_status = "ACCUM"
            elif bd.is_accumulating:
                bd_status = "GOOD"
            elif bd.is_distributing:
                bd_status = "DISTRIB"
            else:
                bd_status = "INFO"
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Bandar", bd_status, bd.label)
            has_detail_rows = True

        if c.fundamentals is not None:
            fund = c.fundamentals
            if fund.is_quality:
                fund_status = "QUALITY"
            elif fund.roe_ttm is not None and fund.roe_ttm >= 10.0:
                fund_status = "GOOD"
            else:
                fund_status = "WEAK"
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Fundam", fund_status, fund.label)
            has_detail_rows = True

        if c.risk_assessment is not None and c.risk_assessment.gate_triggered:
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Risk Block",
                "BAD" if c.risk_assessment.gate_is_structural else "WARN",
                f"{c.risk_assessment.gate_triggered} -> {c.risk_assessment.risk_level_name}",
            )
            has_detail_rows = True

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
        if missing:
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Missing",
                "INFO",
                " ".join(missing),
            )
            has_detail_rows = True
        data_row = [
            _data_freshness(c),
            c.latest_candle_date.isoformat() if c.latest_candle_date else "-",
            c.latest_broker_date.isoformat() if c.latest_broker_date else "-",
            " ".join(missing) if missing else "-",
        ]
        if show_context_ticker:
            data_table.add_row(data_row[0], c.ticker, *data_row[1:])
        else:
            data_table.add_row(*data_row)

        if show_top_broker and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.bci_label == "CLUSTER":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "STABLE":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "RETAIL-LED":
                broker_line += "  [BCI:RETAIL-LED]"
            _add_detail_row(details_table, show_context_ticker, c.ticker, "Broker", "INFO", broker_line.strip())
            has_detail_rows = True

        if c.latest_candle_date is not None and c.latest_broker_date is not None:
            if c.latest_broker_date < c.latest_candle_date:
                lag = trading_sessions_apart(c.latest_broker_date, c.latest_candle_date)
                if lag > 0:
                    _add_detail_row(
                        details_table,
                        show_context_ticker,
                        c.ticker,
                        "Data",
                        "LAG",
                        f"Broker as of {c.latest_broker_date} (+{lag} session{'s' if lag > 1 else ''} behind candle {c.latest_candle_date}) -> saham fetch market {c.ticker} --broker-only",
                    )
                    has_detail_rows = True
            elif c.latest_candle_date < c.latest_broker_date:
                lag = trading_sessions_apart(c.latest_candle_date, c.latest_broker_date)
                if lag > 0:
                    _add_detail_row(
                        details_table,
                        show_context_ticker,
                        c.ticker,
                        "Data",
                        "LAG",
                        f"Candle as of {c.latest_candle_date} (+{lag} session{'s' if lag > 1 else ''} behind broker {c.latest_broker_date}) -> saham fetch market {c.ticker} --candles-only",
                    )
                    has_detail_rows = True

    sections = [
        panel(action_table, title="Candidate Actions"),
        panel(evidence_table, title="Foreign Flow Score"),
        panel(signal_table, title="Signal"),
        panel(
            Group(
                risk_table,
                Text("\nWhy", style="bold cyan"),
                *risk_detail_lines,
                Text(
                    "\nRiskEngine is gate-based: OPEN means no structural/execution gate fired; "
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
            "stockbit  ·  foreign aggregate from IDX  ·  broker detail: inst desk proxy (10 codes, not all-foreign)"
        )
    else:
        meta_table.add_row(
            "Provider",
            f"{response.provider} (aggregate foreign flow)\n"
            "For per-broker detail: run `saham fetch stockbit login`, then fetch with `--provider stockbit`"
        )

    explain_lines = [
        "Candidate Actions is the screen summary. Context panels explain why.",
        "ACCUM is deterministic foreign-flow evidence (0-120). SIGNAL is SignalEngine attractiveness (0-100).",
        "GATE OPEN means no structural/execution risk gate fired; it does not mean the ticker is risk-free.",
        "FLOW% = avg net foreign % of turnover. F_VWAP% positive = price below foreign average buy cost. BB%ILE lower = tighter squeeze.",
    ]
    if strategy_signals is not None:
        explain_lines.append(f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)")

    meta_table.add_row("Definitions", "\n".join(explain_lines))
    meta_table.add_row(
        "Disclaimer",
        "Swing trade watchlist — cross-check with `saham screen pre-open` for intraday entry timing.\n"
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Run Context",
        )
    )
    console().print(_scoring_definitions_panel())


def display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: "date",
    broker_quality = None,
    include_explanation: bool = False,
) -> None:
    """Render multi-window side-by-side table."""
    windows = sorted(results.keys())

    # Build per-ticker dict: ticker -> {window -> candidate}
    by_ticker: dict[str, dict[int, AccumulationCandidate]] = {}
    for w, resp in results.items():
        for c in resp.candidates:
            by_ticker.setdefault(c.ticker, {})[w] = c

    # Apply squeeze filter
    if squeeze_only:
        by_ticker = {
            tk: pw for tk, pw in by_ticker.items()
            if any(
                c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20
                for c in pw.values()
            )
        }

    def sort_key(item: tuple) -> float:
        pw = item[1]
        scores = [c.foreign_flow_score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        try:
            w = int(sort_by.rstrip("ds"))
            c = pw.get(w)
            return c.foreign_flow_score if c else 0.0
        except (ValueError, AttributeError):
            return sum(scores) / len(scores)

    rows = sorted(by_ticker.items(), key=sort_key, reverse=True)[:top_n]

    if not rows:
        empty = compact_table(show_header=False)
        empty.add_column("Message")
        empty.add_row("No candidates found matching the criteria.")
        empty.add_row(f"Next: saham fetch market --universe {universe_label}")
        console().print(
            panel(
                empty,
                title=f"Foreign Accumulation - {universe_label.upper()}",
                subtitle=f"multi-window / {screened_at}",
            )
        )
        return

    table = compact_table()
    table.add_column("#", justify="right")
    table.add_column("Ticker", style="bold")
    for w in windows:
        table.add_column(f"{w}s", justify="right")
    table.add_column("Pattern")
    table.add_column("Trend")
    table.add_column("Broker Flow")

    for i, (tk, pw) in enumerate(rows, 1):
        score_cells = []
        for w in windows:
            candidate = pw.get(w)
            if candidate is None:
                score_cells.append(Text("—", style="bright_black"))
                continue
            style = "green" if candidate.foreign_flow_score >= _ASC.display.enter_min_foreign_flow_score else (
                "yellow" if candidate.foreign_flow_score >= _ASC.display.watch_min_foreign_flow_score else ""
            )
            score_cells.append(Text(f"{candidate.foreign_flow_score:.0f}", style=style))
        pattern = classify_pattern(windows, pw)
        trend = next((c.trend for w in sorted(windows) for c in [pw.get(w)] if c), "—")
        quality = (broker_quality or {}).get(tk)
        brk = quality.label if quality else "n/a"
        table.add_row(str(i), tk, *score_cells, pattern, trend, brk)

    console().print(
        panel(
            table,
            title=f"Foreign Accumulation - {universe_label.upper()}",
            subtitle=f"multi-window / {screened_at}",
        )
    )

    if not include_explanation:
        return

    # Render run context cleanly in a second panel
    meta_table = compact_table(show_header=False)
    meta_table.add_column("Key", style="bold cyan")
    meta_table.add_column("Value")

    sample_resp = next(iter(results.values()))
    meta_table.add_row(
        "Stats",
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )

    meta_table.add_row(
        "Scores",
        "Accum ≥70 green | ≥40 yellow | <40 white"
    )

    meta_table.add_row(
        "Patterns",
        "sustained | building | fresh rotation | long-term only | coiled spring | weak"
    )

    meta_table.add_row(
        "Broker Flow",
        "5-session named top-broker bucket: smart+/noise+ = net buying, smart-/noise- = net selling, n/a = no detail"
    )

    meta_table.add_row(
        "Disclaimer",
        "DISCLAIMER: Analysis only, not trading advice."
    )

    console().print(
        panel(
            meta_table,
            title="Run Context",
        )
    )


def print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""
    # Top introductory text
    intro = Text(
        "Detects stocks being quietly bought by foreign institutions over\n"
        "multiple days. When foreigners accumulate consistently AND are\n"
        "'underwater' (bought higher than today's price), IHSG stocks\n"
        "resolve upward 65–70% of the time within 10–20 trading days.\n"
        "This is a swing trade watchlist (5–20 day horizon).\n",
        style="italic"
    )

    # Aligned Guide Table
    guide_table = compact_table()
    guide_table.add_column("Signal / Metric", style="bold yellow", width=22)
    guide_table.add_column("Value / Bench", style="cyan", width=20)
    guide_table.add_column("Details & Mechanics")

    guide_table.add_row(
        "SCORE (0–120)",
        "≥ 70 (green)\n40-69 (yellow)\n< 40 (white)",
        "Composite signal strength. Combines net days, streak, VWAP, RSI, flow, BB width, and BCI into a single score.\n- Green: Strong signal, worth research.\n- Yellow: Moderate watch, wait for confirmation.\n- White: Weak, likely noise, skip."
    )
    guide_table.add_row(
        "STREAK",
        "1-2d\n3-4d\n5-7d\n8d+",
        "Consecutive trading days foreigners were net buyers.\n- 5-7d: Strong, likely intentional.\n- 8d+: Very strong, committed.\nScoring: exponential curve (τ=7d). 7d ≈ 63%, 14d ≈ 86%."
    )
    guide_table.add_row(
        "NET_DAYS",
        "100%\n70-99%\n50-69%\n< 50%",
        "Consistency Ratio (net buy days / total sessions in window).\n- 100%: Every day was positive buy.\n- 70-99%: Most days positive.\n- < 50%: More sells than buys (not accumulating)."
    )
    guide_table.add_row(
        "NET_VALUE",
        "+19.4B\n+10M",
        "Total net foreign flow (buys − sells) in IDR over the window.\nConfirms real capital size behind the streak.\nT = trillion | B = billion | M = million (IDR)."
    )
    guide_table.add_row(
        "FLOW%",
        "0-5%\n5-15%\n15-30%\n30%+",
        "Average net foreign % of total daily turnover.\nA mid-cap at 35% FLOW% is a stronger signal than a large-cap at 3%.\nScoring: up to 10 pts, saturates at 20% flow ratio."
    )
    guide_table.add_row(
        "F_VWAP%",
        "> +5% (green)\n+1% to +5%\n< 0%",
        "Foreigners' VWAP to today's close price percentage.\n- Positive: foreigners bought higher than today's price (underwater, motivated to defend position).\n- Negative: foreigners in profit.\nScoring: 10% underwater = 20 pts."
    )
    guide_table.add_row(
        "RSI (14-day)",
        "> 70\n55-70\n40-55\n25-40\n< 25",
        "Relative Strength Index (0–100).\n- 25-40: Ideal entry zone.\n- > 70: Overbought.\nScoring: peak at RSI=40 (10 pts), zero at RSI≤25 or ≥75."
    )
    guide_table.add_row(
        "BB%ILE",
        "≤ 20% (green)\n21-40% (yellow)\n> 40%",
        "Bollinger Band width percentile vs last 60 days.\n- ≤ 20%: Squeeze (coiled spring, volatility compressed, ready to break).\nNot scored in default foreign-flow score (setup/structure evidence only)."
    )
    guide_table.add_row(
        "TREND",
        "UP\nDOWN\nSIDE",
        "Price relative to SMA20 (UP = >2% above, DOWN = >2% below, SIDE = within ±2%).\nDOWN or SIDE is often ideal to enter before the breakout."
    )
    guide_table.add_row(
        "PATTERN",
        "sustained\nbuilding\nfresh rotation\ncoiled spring",
        "Multi-window 7d/30d/90d evaluation.\n- sustained: score ≥60 on all windows.\n- building: strong 7d+30d, weak 90d.\n- coiled spring: BB squeeze + score ≥60 on any window."
    )
    guide_table.add_row(
        "EVIDENCE PTS",
        "cons / streak / vwap\nrsi / flow / bb / inst",
        "Foreign-flow score components: cons (40 pts), streak (30 pts), vwap (20 pts), rsi (10 pts), flow (10 pts), inst (15 pts BCI). bb shown diagnostically — not scored by default."
    )

    checklist_text = Text(
        "  1. PATTERN = sustained or coiled spring  (multi-window confirms)\n"
        "  2. STREAK ≥ 5d                          (systematic, not opportunistic)\n"
        "  3. F_VWAP% > 0%                         (foreigners defending position)\n"
        "  4. BB%ILE ≤ 20% (green)                 (compressed, spring loaded)\n"
        "  5. RSI between 30–50                    (room to run)\n"
        "  6. FLOW% > 15%                          (foreigners dominating volume)\n"
        "  7. NET_DAYS ≥ 70%                       (consistent, not just a streak)",
        style="green"
    )

    tips_text = Text(
        "  • Run --multi first for the daily overview — one command, three windows.\n"
        "  • Use --squeeze-only to surface 'coiled spring' setups.\n"
        "  • Deep-dive: saham view broker flow <TICKER> --days 30\n"
        "               saham analyze risk <TICKER> --with-sentiment",
        style="cyan"
    )

    console().print(
        panel(
            Group(
                intro,
                Text("Signals & Metrics Breakdown", style="bold cyan"),
                guide_table,
                Text("\nIdeal Candidate Checklist (Priority Order)", style="bold cyan"),
                checklist_text,
                Text("\nQuick Tips", style="bold cyan"),
                tips_text,
                Text("\nDISCLAIMER: Analysis only. Not financial advice.", style="dim italic")
            ),
            title="FOREIGN ACCUMULATION SCREENER — COLUMN GUIDE",
        )
    )
