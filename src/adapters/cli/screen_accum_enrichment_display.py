"""
Enrichment and details table display helpers for accumulation screen.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from src.adapters.cli.rich_display import compact_table
from src.adapters.cli.screen_accum_formatters import (
    AccumulationDisplayConfig,
    format_disc_pct_plain,
    notation_detail,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.domain.services.trading_calendar import trading_sessions_apart


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


def _add_detail_row(
    table: Any, show_ticker: bool, ticker: str, kind: str, status: str, detail: str
) -> None:
    row = [kind]
    if show_ticker:
        row.append(ticker)
    row.extend([_detail_status(status), detail])
    table.add_row(*row)


def _evidence_factor_rows(
    candidate: AccumulationCandidate,
    display_config: AccumulationDisplayConfig
) -> list[tuple[str, ...]]:
    bd = (
        candidate.foreign_flow_score_breakdown.breakdown_dict
        if candidate.foreign_flow_score_breakdown else {}
    )
    rsi = f"{candidate.rsi:.1f}" if candidate.rsi is not None else "-"
    flow = f"{candidate.avg_flow_ratio:+.1f}%" if candidate.avg_flow_ratio is not None else "-"
    vwap = format_disc_pct_plain(candidate.vwap_discount_pct)
    bb = (
        f"{candidate.bb_width_pctile * 100:.0f}%"
        if candidate.bb_width_pctile is not None else "-"
    )
    bb_scored = display_config.foreign_flow_score_policy.bb_squeeze.enabled

    def _pts(key: str) -> str:
        value = bd.get(key)
        return f"{value:.1f}" if value is not None else "—"

    bb_pts = _pts("bb") if bb_scored else "—"
    bb_means = (
        "Volatility squeeze" if bb_scored
        else "Setup compression diagnostic, not flow score"
    )
    return [
        (
            _pts("cons"),
            "Net days",
            f"{candidate.net_buy_days}/{candidate.total_days}",
            "Foreign buy consistency",
        ),
        (
            _pts("streak"),
            "Streak",
            f"{candidate.consecutive_streak}s",
            "Current buy run",
        ),
        (
            _pts("vwap"),
            "F_VWAP%",
            vwap,
            "Foreign avg cost vs price (soft depth badge)",
        ),
        (
            _pts("rsi"),
            "RSI",
            rsi,
            "Entry headroom",
        ),
        (
            _pts("flow"),
            "Flow%",
            flow,
            "Foreign share of turnover",
        ),
        (
            bb_pts,
            "BB%ile",
            bb,
            bb_means,
        ),
        (
            _pts("inst"),
            "BCI",
            _format_bci_status(candidate),
            "Tier-1 broker concentration",
        ),
    ]


def _format_bci_status(candidate: AccumulationCandidate) -> str:
    """BCI label plus diagnostic absorption ratio when aggregate is net-selling."""
    label = candidate.bci_label or "-"
    ratio = candidate.bci_absorption_ratio
    if ratio is None:
        return label
    return f"{label} (abs={ratio:.2f})"


def build_enrichment_details_table(
    candidates: list[AccumulationCandidate],
    show_context_ticker: bool,
    show_top_broker: bool,
) -> tuple[Any, bool]:
    """Build the 'Enrichment Details' table containing corporate action, insider, analyst,

    shareholding, bandar, fundamentals, earnings, broker detail, valuation, and evidence-factor
    detail rows.
    """
    details_table = compact_table()
    details_table.add_column("Type")
    if show_context_ticker:
        details_table.add_column("Ticker", style="bold")
    details_table.add_column("Status")
    details_table.add_column("Detail")

    has_detail_rows = False

    for c in candidates:
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
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Corp Act",
                "WARN",
                "Dividend risk inside hold window",
            )
            has_detail_rows = True
        if c.rights_issue_risk:
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Corp Act",
                "WARN",
                "Rights issue inside hold window",
            )
            has_detail_rows = True
        if c.insider_buying:
            for label in c.recent_insider_buys:
                _add_detail_row(
                    details_table, show_context_ticker, c.ticker, "Insider", "BUY", label
                )
                has_detail_rows = True

        if c.analyst_consensus is not None:
            ac = c.analyst_consensus
            if ac.is_bullish and (ac.upside_pct or 0) >= 10:
                ac_status = "BULLISH"
            elif ac.sell_count > ac.buy_count:
                ac_status = "BEARISH"
            else:
                ac_status = "INFO"
            _add_detail_row(
                details_table, show_context_ticker, c.ticker, "Analyst", ac_status, ac.label
            )
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
            _add_detail_row(
                details_table, show_context_ticker, c.ticker, "Bandar", bd_status, bd.label
            )
            has_detail_rows = True

        if c.fundamentals is not None:
            fund = c.fundamentals
            if fund.is_quality:
                fund_status = "QUALITY"
            elif fund.roe_ttm is not None and fund.roe_ttm >= 10.0:
                fund_status = "GOOD"
            else:
                fund_status = "WEAK"
            _add_detail_row(
                details_table, show_context_ticker, c.ticker, "Fundam", fund_status, fund.label
            )
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

        if show_top_broker and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.bci_label == "CLUSTER":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "STABLE":
                broker_line += f"  [BCI:{c.bci_label}({c.bci_tier1_count}T1)]"
            elif c.bci_label == "RETAIL-LED":
                broker_line += "  [BCI:RETAIL-LED]"
            if c.bci_absorption_ratio is not None:
                broker_line += f" [abs={c.bci_absorption_ratio:.2f}]"
            _add_detail_row(
                details_table,
                show_context_ticker,
                c.ticker,
                "Broker",
                "INFO",
                broker_line.strip(),
            )
            has_detail_rows = True

        if c.latest_candle_date is not None and c.latest_broker_date is not None:
            if c.latest_broker_date < c.latest_candle_date:
                lag = trading_sessions_apart(c.latest_broker_date, c.latest_candle_date)
                if lag > 0:
                    msg = (
                        f"Broker as of {c.latest_broker_date} (+{lag} "
                        f"session{'s' if lag > 1 else ''} behind candle "
                        f"{c.latest_candle_date}) -> saham fetch market {c.ticker} "
                        "--broker-only"
                    )
                    _add_detail_row(
                        details_table,
                        show_context_ticker,
                        c.ticker,
                        "Data",
                        "LAG",
                        msg,
                    )
                    has_detail_rows = True
            elif c.latest_candle_date < c.latest_broker_date:
                lag = trading_sessions_apart(c.latest_candle_date, c.latest_broker_date)
                if lag > 0:
                    msg = (
                        f"Candle as of {c.latest_candle_date} (+{lag} "
                        f"session{'s' if lag > 1 else ''} behind broker "
                        f"{c.latest_broker_date}) -> saham fetch market {c.ticker} "
                        "--candles-only"
                    )
                    _add_detail_row(
                        details_table,
                        show_context_ticker,
                        c.ticker,
                        "Data",
                        "LAG",
                        msg,
                    )
                    has_detail_rows = True

    return details_table, has_detail_rows
