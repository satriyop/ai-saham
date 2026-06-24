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


def style_classification(value: str) -> str:
    if value == "ENTER":
        return typer.style(value, fg=typer.colors.GREEN, bold=True)
    if value == "WATCH":
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


def format_failed_gates_summary(preset_eval: Any) -> str:
    return "Failed gates: " + "; ".join(preset_eval.failed_reasons)


def swing_summary_parts(
    accum: Any | None,
    risk_resp: Any,
    backtest_result: Any,
    sentiment_resp: Any,
) -> list[str]:
    parts = []
    if accum:
        parts.append(f"Score {accum.score:.1f}")
    if risk_resp:
        parts.append(risk_resp.assessment.risk_level_name)
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
    preset_eval: Any | None,
    preset_sizing: Any | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
    config: SwingDisplayConfig,
) -> tuple[str, str]:
    strategy_override = (
        strategy_risk_level == "HIGH_RISK"
        and preset_eval is not None
        and preset_eval.passed
    )

    if preset_eval is not None:
        if strategy_override:
            return (
                f"AVOID (strategy gate: '{strategy_risk_name}' signals HIGH_RISK; preset passed but technical signal says exit).",
                "red",
            )
        if preset_eval.passed and preset_sizing and preset_sizing.lots > 0:
            return (
                f"ENTER setup passed. Consider {preset_sizing.lots} lots at "
                f"{float(preset_sizing.entry_price):,.0f}; TP "
                f"{float(preset_sizing.target_price):,.0f}; SL "
                f"{float(preset_sizing.stop_price):,.0f}; max hold "
                f"{config.foreign_bounce_max_hold_days} trading days.",
                "green",
            )
        if preset_eval.passed:
            return ("ENTER setup passed. Add --capital to compute lot size.", "green")
        if preset_eval.classification == "WATCH":
            return (
                "WATCH only. Preset is close but not fully confirmed; wait for failed gates to improve.",
                "yellow",
            )
        return ("AVOID. Preset gates are not aligned.", "red")
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
    return ("No action plan available from current inputs.", "bright_black")


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


def print_swing_rich_overview(
    ticker: str,
    today: date,
    profile: str,
    strategy_name: str,
    data_freshness: DataFreshness,
    broker_detail: BrokerDetail | None,
    accum: AccumulationCandidate | None,
    risk_resp,
    atr_value: Decimal | None,
    sizing: SizingResult | None,
    preset_eval: PresetEvaluation | None,
    preset_sizing: PercentSizingResult | None,
    broker_quality_note: BrokerQualityNote | None,
    market_regime: MarketContext | None,
    capital: int | None,
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
    config: SwingDisplayConfig,
) -> None:
    summary_parts = swing_summary_parts(accum, risk_resp, backtest_result, sentiment_resp)
    summary_text = " · ".join(summary_parts) if summary_parts else "insufficient data for assessment"
    plan_text, plan_style = swing_plan_text(
        ticker,
        capital,
        atr_value,
        sizing,
        preset_eval,
        preset_sizing,
        strategy_risk_level,
        strategy_risk_name,
        config,
    )

    data_table = compact_table(show_header=False)
    data_table.add_column("Metric", style="bold")
    data_table.add_column("Value")
    data_table.add_row("Analysis date", str(today))
    data_table.add_row("Profile", profile)
    data_table.add_row("Strategy", strategy_name)
    data_table.add_row("Candles through", fmt_date(data_freshness.candle_end))
    data_table.add_row("Broker flow through", fmt_date(data_freshness.broker_end))
    if market_regime is not None:
        _label = REGIME_DISPLAY_LABEL.get(market_regime.regime.value, market_regime.regime.value)
        _score = context_conviction_score(market_regime)
        data_table.add_row("Market regime", f"{_label} ({_score}/7)")
    notation_text = notation_detail(accum.ticker_notation) if accum is not None else ""
    if notation_text:
        data_table.add_row("Notation", notation_text)

    decision = compact_table(show_header=False)
    decision.add_column("Label", style="bold")
    decision.add_column("Value")
    decision.add_row("SUMMARY:", Text(summary_text, style="bold"))
    decision.add_row("PLAN:", Text(plan_text, style=f"bold {plan_style}"))

    signals = compact_table()
    signals.add_column("Signal", style="bold")
    signals.add_column("Status")
    signals.add_column("Detail")
    if accum is not None:
        signals.add_row(
            "Accumulation",
            f"{accum.score:.1f}",
            f"streak {accum.consecutive_streak}s; trend {accum.trend}; flow {fmt_pct(accum.avg_flow_ratio, True)}",
        )
    else:
        signals.add_row("Accumulation", "missing", f"Run: saham fetch broker {ticker}")
    if preset_eval is not None:
        failed = "; ".join(preset_eval.failed_reasons[:2]) if preset_eval.failed_reasons else "all gates passed"
        signals.add_row("Preset", preset_eval.classification, failed)
    if accum is not None and accum.ticker_notation is not None:
        note_status = notation_label(accum.ticker_notation)
        if note_status != "-":
            signals.add_row("Notation", note_status, notation_detail(accum.ticker_notation))
    if risk_resp is not None:
        r = risk_resp.assessment
        signals.add_row("Risk", r.risk_level_name, f"confidence {r.confidence}/100")
    if broker_detail is not None:
        signals.add_row("Broker quality", broker_detail.quality, broker_detail.broker_weight_quality)
    if broker_quality_note is not None:
        signals.add_row("Broker note", broker_quality_note.level, broker_quality_note.message)
    if sentiment_resp and not sentiment_resp.warning:
        snap = sentiment_resp.snapshot
        signals.add_row(
            "Sentiment",
            snap.overall_sentiment.value.upper(),
            f"{snap.total_count} headlines; confidence {snap.confidence_pct}%",
        )
    elif sentiment_warning:
        signals.add_row("Sentiment", "unavailable", sentiment_warning)
    if backtest_result is not None and backtest_result.trade_count > 0:
        signals.add_row(
            "History",
            f"{backtest_result.trade_count} trades",
            f"WR {float(backtest_result.win_rate):.1f}%; PF {float(backtest_result.profit_factor):.2f}",
        )

    sections = [
        Text("Decision", style="bold cyan"),
        decision,
        Text("Data Freshness", style="bold cyan"),
        data_table,
        Text("Signal Snapshot", style="bold cyan"),
        signals,
    ]

    chosen_sizing = preset_sizing or sizing
    if capital is not None and chosen_sizing is not None:
        sizing_table = compact_table(show_header=False)
        sizing_table.add_column("Metric", style="bold")
        sizing_table.add_column("Value")
        sizing_table.add_row("Capital", f"{capital:,.0f} IDR")
        sizing_table.add_row("Entry", f"{float(chosen_sizing.entry_price):,.0f}")
        sizing_table.add_row("Stop", f"{float(chosen_sizing.stop_price):,.0f}")
        sizing_table.add_row("Target", f"{float(chosen_sizing.target_price):,.0f}")
        sizing_table.add_row("Lots", f"{chosen_sizing.lots:,}")
        sections.extend([Text("Sizing", style="bold cyan"), sizing_table])

    warnings = list(data_freshness.warnings)
    if market_regime is not None:
        warnings.extend(context_warnings(market_regime))
    if warnings:
        warning_table = compact_table(show_header=False)
        warning_table.add_column("Warning")
        for warning in warnings[:5]:
            warning_table.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warning_table])

    console().print(
        panel(
            Group(*sections),
            title=f"Swing Decision - {ticker}",
            subtitle=f"{today.isoformat()} / {profile}",
        )
    )





def print_swing_output(
    ticker: str,
    today: date,
    profile: str,
    strategy_name: str,
    data_freshness: DataFreshness,
    flow_detail: FlowDetail | None,
    broker_detail: BrokerDetail | None,
    window: int,
    accum: "AccumulationCandidate | None",
    risk_resp,
    atr_value: "Decimal | None",
    sizing: "SizingResult | None",
    preset_eval: "PresetEvaluation | None",
    preset_sizing: "PercentSizingResult | None",
    broker_quality_note: BrokerQualityNote | None,
    market_regime: "MarketContext | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    sentiment_verbose: bool,
    no_backtest: bool,
    no_sentiment: bool,
    strategy_risk_level: str | None = None,
    strategy_risk_name: str | None = None,
    signal_assessment=None,
    config: SwingDisplayConfig | None = None,
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
        profile=profile,
        strategy_name=strategy_name,
        data_freshness=data_freshness,
        broker_detail=broker_detail,
        accum=accum,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        preset_eval=preset_eval,
        preset_sizing=preset_sizing,
        broker_quality_note=broker_quality_note,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=sentiment_warning,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        config=config,
    )

    # ── Panel 2: DETAILED MARKET & RISK CONTEXT ─────────────────────────────
    regime_text = []
    if market_regime is not None:
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
    if risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        risk_text.append(Text(f"Risk Confirmation Verdict: {r.risk_level_name} (Confidence: {r.confidence}/100)", style="bold cyan"))
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
    else:
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
            strat_text.append(Text(f"⚠ Strategy '{strategy_risk_name}' signals HIGH_RISK — overrides preset to AVOID.", style="red"))
        elif strategy_risk_level == "LOW_RISK":
            strat_text.append(Text(f"✓ Strategy '{strategy_risk_name}' confirms entry signal.", style="green"))
        else:
            strat_text.append(Text(f"~ Strategy '{strategy_risk_name}' is neutral — no override.", style="dim"))

    signal_text = []
    if signal_assessment is not None:
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
        for line in sa.rationale[-3:]:
            signal_text.append(Text(f"  {line}", style="dim"))
        if signal_assessment.coverage_warning:
            signal_text.append(Text(f"  ⚠ {signal_assessment.coverage_warning}", style="dim yellow"))

    context_group = []
    if regime_text:
        context_group.extend(regime_text)
    if risk_text:
        if context_group:
            context_group.append(Text(""))
        context_group.extend(risk_text)
    if strat_text:
        if context_group:
            context_group.append(Text(""))
        context_group.extend(strat_text)
    if signal_text:
        if context_group:
            context_group.append(Text(""))
        context_group.extend(signal_text)

    if context_group:
        console().print("")
        console().print(
            panel(
                Group(*context_group),
                title="DETAILED MARKET & RISK CONTEXT",
            )
        )

    # ── Panel 3: DETAILED FOREIGN FLOW & BROKER ATTRIBUTION ────────────────
    flow_group = []
    if accum:
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

        # Earnings history — read from cache only (no live fetch in display layer)
        try:
            from pathlib import Path as _Path

            from src.infrastructure.browser.stockbit_earnings import StockbitEarningsProvider
            from src.infrastructure.config.app_config import APP_CFG as _app_cfg
            _db = _Path(_app_cfg.storage.db_path)
            _ep = StockbitEarningsProvider(broker_provider=None, db_path=_db)
            _earnings = _ep.get_earnings_history(accum.ticker, quarters=4)
            if _earnings:
                beat_streak = sum(1 for r in _earnings if r.beat is True)
                miss_streak = sum(1 for r in _earnings if r.beat is False)
                _labels = "  |  ".join(r.label for r in _earnings[:4])
                if beat_streak >= 3:
                    e_color = "green"
                elif miss_streak >= 3:
                    e_color = "red"
                else:
                    e_color = "white"
                corp_flags.append(Text(f"💰 EARNINGS ({beat_streak}/{len(_earnings)} beat): {_labels}", style=e_color))
        except Exception:
            pass

        # Valuation metrics — read from cache only
        try:
            from pathlib import Path as _Path2

            from src.infrastructure.browser.stockbit_valuation import StockbitValuationProvider
            from src.infrastructure.config.app_config import APP_CFG as _app_cfg2
            _db2 = _Path2(_app_cfg2.storage.db_path)
            _vp = StockbitValuationProvider(broker_provider=None, db_path=_db2)
            _val = _vp.get_valuation(accum.ticker)
            if _val and not _val.is_empty:
                _parts = [f"{label} {v:.2f}" for label, v in _val.labeled]
                if _parts:
                    corp_flags.append(Text(f"💲 VALUATION: {' | '.join(_parts)}", style="cyan"))
        except Exception:
            pass

        if corp_flags:
            flow_group.append(Text("\nAdditional Signals & Flags", style="bold cyan"))
            for flag in corp_flags:
                flow_group.append(flag)

    if flow_detail:
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

    if broker_detail:
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
                title="DETAILED FOREIGN FLOW & BROKER ATTRIBUTION",
            )
        )

    # ── Panel 4: PRESET RULE AUDITS & GATES ───────────────────────────────────
    if preset_eval is not None:
        gates_group = []
        gates_group.append(Text(f"Preset Rules Evaluation: {preset_eval.name}", style="bold cyan"))

        gates_table = compact_table()
        gates_table.add_column("Status")
        gates_table.add_column("Gate Rule", style="bold")
        gates_table.add_column("Actual Value")
        gates_table.add_column("Required Threshold")

        for gate in preset_eval.gates:
            status_str = "[green]PASS[/]" if gate.passed else "[red]FAIL[/]"
            gates_table.add_row(
                status_str,
                gate.label,
                str(gate.actual),
                str(gate.required)
            )
        gates_group.append(gates_table)

        if preset_eval.passed:
            gates_group.append(Text("✓ All gates successfully passed. Tested plan: TP +5%, SL -5%, max hold 10 trading days.", style="green"))
        else:
            gates_group.append(Text(f"⚠ {format_failed_gates_summary(preset_eval)}", style="red"))

        if broker_quality_note is not None:
            note_style = "yellow" if broker_quality_note.level == "warning" else "cyan"
            gates_group.append(Text(f"★ {broker_quality_note.message}", style=note_style))

        console().print("")
        console().print(
            panel(
                Group(*gates_group),
                title="PRESET RULE AUDITS & GATES",
            )
        )

    # ── Panel 5: DETAILED HISTORY & SENTIMENT ─────────────────────────────────
    history_sentiment_group = []

    # Backtest segment
    history_group = []
    if backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        history_group.append(Text(f"Historical Backtest ({strategy_name}): {r.trade_count} trades", style="bold cyan"))
        hist_table = compact_table()
        hist_table.add_column("Win Rate")
        hist_table.add_column("Profit Factor")
        hist_table.add_column("Max Drawdown")
        hist_table.add_column("Avg Win")
        hist_table.add_column("Avg Loss")

        win_style = "green" if float(r.win_rate) >= 55 else ("yellow" if float(r.win_rate) >= 45 else "red")
        avg_win_val = f"{float(r.avg_win):,.0f} IDR" if r.avg_win else "—"
        avg_loss_val = f"{float(r.avg_loss):,.0f} IDR" if r.avg_loss else "—"

        hist_table.add_row(
            f"[{win_style}]{float(r.win_rate):.1f}%[/]",
            f"{float(r.profit_factor):.2f}",
            f"{float(r.max_drawdown_pct):.1f}%",
            avg_win_val,
            avg_loss_val
        )
        history_group.append(hist_table)
    elif backtest_result is not None and backtest_result.trade_count == 0:
        history_group.append(Text(f"Historical Backtest ({strategy_name})", style="bold cyan"))
        history_group.append(Text("No trades triggered in available history (needs more broker data).", style="dim"))
        history_group.append(Text(f"Tip: run `saham backtest {ticker} --strategy {strategy_name} --verbose`", style="dim italic"))
    elif not no_backtest:
        history_group.append(Text("Historical Backtest", style="bold cyan"))
        history_group.append(Text(f"Could not run backtest. Run: `saham fetch market {ticker} --days 730`", style="dim yellow"))

    if history_group:
        history_sentiment_group.extend(history_group)

    # Sentiment segment
    if not no_sentiment:
        if history_sentiment_group:
            history_sentiment_group.append(Text(""))
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

        history_sentiment_group.extend(sentiment_group)

    if history_sentiment_group:
        console().print("")
        console().print(
            panel(
                Group(*history_sentiment_group),
                title="DETAILED HISTORY & SENTIMENT",
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

