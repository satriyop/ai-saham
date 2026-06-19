"""
Swing analysis display helper functions.

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

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    fmt_broker_detail_lines,
    fmt_money_short,
    fmt_money_short_signed,
)


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
    market_regime: MarketRegimeResponse | None,
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
        data_table.add_row("Market regime", f"{market_regime.label} ({market_regime.score}/7)")
    notation_text = notation_detail(accum.ticker_notation) if accum is not None else ""
    if notation_text:
        data_table.add_row("Notation", notation_text)

    decision = compact_table(show_header=False)
    decision.add_column("Label", style="bold")
    decision.add_column("Value")
    decision.add_row("SUMMARY", Text(summary_text, style="bold"))
    decision.add_row("PLAN", Text(plan_text, style=f"bold {plan_style}"))

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
        warnings.extend(market_regime.warnings)
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
    market_regime: "MarketRegimeResponse | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    sentiment_verbose: bool,
    no_backtest: bool,
    no_sentiment: bool,
    strategy_risk_level: str | None = None,
    strategy_risk_name: str | None = None,
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

    typer.echo("")
    sep("=")
    typer.echo(typer.style(
        f"SWING VIEW — {ticker} · {today} · profile={profile}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    sep("=")

    # ── DATA FRESHNESS ──────────────────────────────────────────────────────
    typer.echo("")
    section_header("DATA")
    typer.echo(
        f"  Analysis date  {fmt_date(data_freshness.as_of_date)}   "
        f"Candles through  {fmt_date(data_freshness.candle_end)}   "
        f"Broker flow through  {fmt_date(data_freshness.broker_end)}"
    )
    if market_regime is not None:
        typer.echo(f"  Regime as of   {fmt_date(market_regime.as_of_date)}")
    if data_freshness.refresh_actions:
        typer.echo("  Refresh        " + "; ".join(data_freshness.refresh_actions))
    if data_freshness.warnings:
        for warning in data_freshness.warnings[:3]:
            typer.echo(typer.style(f"  ! {warning}", fg=typer.colors.YELLOW))

    # ── ACCUMULATION ─────────────────────────────────────────────────────────
    typer.echo("")
    if accum:
        label = signal_label(accum, config)
        section_header(
            f"ACCUMULATION ({window} sessions)",
            f"signal: {typer.style(label, bold=label in ('strong', 'coiled spring'))}",
        )
        flow_str = (
            f"{accum.avg_flow_ratio:+.1f}%"
            if accum.avg_flow_ratio is not None else "—"
        )
        fvwap_str = (
            f"{accum.vwap_discount_pct:+.1f}%"
            if accum.vwap_discount_pct is not None else "—"
        )
        vwap_pct_str = (
            typer.style(f"{accum.vwap_pct:+.1f}%", fg=typer.colors.GREEN)
            if accum.vwap_pct is not None and accum.vwap_pct < 0
            else (f"{accum.vwap_pct:+.1f}%" if accum.vwap_pct is not None else "—")
        )
        bb_str = style_bb(accum.bb_width_pctile) if accum.bb_width_pctile is not None else "—"
        net_str = f"{accum.net_buy_days}/{accum.total_days}"

        typer.echo(
            f"  Score  {style_score(accum.score, config)}   "
            f"STREAK  {accum.consecutive_streak}s   "
            f"NET_DAYS  {net_str}   "
            f"FLOW%  {flow_str}"
        )
        typer.echo(
            f"  F_VWAP%  {fvwap_str}    "
            f"VWAP%  {vwap_pct_str}    "
            f"BB%ILE  {bb_str}    "
            f"TREND  {style_trend(accum.trend)}"
        )
        if accum.score_breakdown:
            bd = accum.score_breakdown
            typer.echo(typer.style(
                f"  [cons={bd.get('cons',0):.1f} streak={bd.get('streak',0):.1f}"
                f" vwap={bd.get('vwap',0):.1f} rsi={bd.get('rsi',0):.1f}"
                f" flow={bd.get('flow',0):.1f} bb={bd.get('bb',0):.1f}]",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        notation_text = notation_detail(accum.ticker_notation)
        if notation_text:
            color = typer.colors.YELLOW if accum.ticker_notation and accum.ticker_notation.has_warning else typer.colors.WHITE
            typer.echo(typer.style(f"  NOTATION  {notation_text}", fg=color))

        # Corp action risk flags
        if accum.dividend_risk:
            typer.echo(typer.style("  ⚠ DIVIDEND RISK — ex-date within hold window", fg=typer.colors.YELLOW))
        if accum.rights_issue_risk:
            typer.echo(typer.style("  ⚠ RIGHTS ISSUE — dilution risk within hold window", fg=typer.colors.YELLOW))
        for rups_detail in accum.upcoming_rups:
            typer.echo(typer.style(f"  ★ RUPS upcoming — {rups_detail}", fg=typer.colors.CYAN))
        # Seasonality signal
        if accum.seasonal_edge is not None:
            se = accum.seasonal_edge
            se_color = typer.colors.GREEN if se.is_tailwind else (typer.colors.RED if se.is_headwind else typer.colors.WHITE)
            typer.echo(typer.style(
                f"  SEASONAL  {se.label}  (score {se.score:+.2f})",
                fg=se_color,
            ))
        # Insider buying flag
        if accum.insider_buying:
            for label in accum.recent_insider_buys:
                typer.echo(typer.style(f"  ⭐ INSIDER BUY — {label}", fg=typer.colors.CYAN))

        # Analyst consensus
        if accum.analyst_consensus is not None:
            ac = accum.analyst_consensus
            if ac.is_bullish and (ac.upside_pct or 0) >= 10:
                ac_color = typer.colors.GREEN
            elif ac.sell_count > ac.buy_count:
                ac_color = typer.colors.RED
            else:
                ac_color = typer.colors.WHITE
            typer.echo(typer.style(f"  📊 ANALYST: {ac.label}", fg=ac_color))

        # Shareholding composition
        if accum.shareholding is not None:
            sh = accum.shareholding
            sh_color = typer.colors.CYAN if sh.institution_pct >= 30.0 else typer.colors.WHITE
            typer.echo(typer.style(f"  🏦 HOLDING: {sh.label}", fg=sh_color))

        # Bandar detector — Stockbit's institutional operator accumulation signal
        if accum.bandar_detector is not None:
            bd = accum.bandar_detector
            if bd.accumulation_score >= 4:
                bd_color = typer.colors.GREEN
            elif bd.is_accumulating:
                bd_color = typer.colors.YELLOW
            elif bd.is_distributing:
                bd_color = typer.colors.RED
            else:
                bd_color = typer.colors.WHITE
            typer.echo(typer.style(f"  🔍 BANDAR: {bd.label}", fg=bd_color))

        # Company fundamentals — P/E, ROE, NPM, Piotroski F-Score
        if accum.fundamentals is not None:
            fund = accum.fundamentals
            if fund.is_quality:
                fund_color = typer.colors.GREEN
            elif fund.roe_ttm is not None and fund.roe_ttm >= 10.0:
                fund_color = typer.colors.YELLOW
            else:
                fund_color = typer.colors.RED
            typer.echo(typer.style(f"  📈 FUNDAM: {fund.label}", fg=fund_color))
    else:
        section_header(f"ACCUMULATION ({window} sessions)")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham fetch broker {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── BROKER FLOW DETAIL (institutional desk proxy — 10 codes, not all-foreign) ──────────
    typer.echo("")
    if flow_detail:
        section_header(
            f"FLOW DETAIL ({flow_detail.window_sessions} sessions)",
            f"through: {fmt_date(flow_detail.through_date)} · institutional desk",
        )
        typer.echo(
            f"  Range  {fmt_date(flow_detail.from_date)} → "
            f"{fmt_date(flow_detail.through_date)}   "
            f"Sessions  {flow_detail.available_sessions}/{flow_detail.window_sessions}"
        )
        typer.echo(
            f"  Net    {fmt_money_short(flow_detail.total_net_flow)} IDR   "
            f"BUY/SELL  {flow_detail.buy_sessions}/{flow_detail.sell_sessions}   "
            f"STREAK  {flow_detail.consecutive_buy_sessions}s"
        )
        latest_flow = (
            fmt_money_short(flow_detail.latest_net_flow)
            if flow_detail.latest_net_flow is not None else "N/A"
        )
        typer.echo(
            f"  Avg FLOW%  {fmt_pct(flow_detail.avg_flow_ratio_pct, True)}   "
            f"Latest  {latest_flow} "
            f"({fmt_pct(flow_detail.latest_flow_ratio_pct, True)})"
        )
    else:
        section_header("FLOW DETAIL")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham fetch broker {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── NAMED BROKER DETAIL ────────────────────────────────────────────────
    if broker_detail:
        typer.echo("")
        section_header(
            f"BROKER DETAIL ({broker_detail.detail_sessions}/{broker_detail.window_sessions} sessions)",
            f"through: {fmt_date(broker_detail.through_date)} · {broker_detail.source}",
        )
        typer.echo(f"  Top buyers       {fmt_broker_detail_lines(broker_detail.top_buyers)}")
        typer.echo(f"  Top sellers      {fmt_broker_detail_lines(broker_detail.top_sellers)}")
        typer.echo(
            f"  Smart flow       {fmt_money_short_signed(broker_detail.smart_flow)} IDR   "
            f"Noise flow  {fmt_money_short_signed(broker_detail.noise_flow)} IDR"
        )
        smart_share = (
            f"{broker_detail.smart_share_pct:.1f}%"
            if broker_detail.smart_share_pct is not None else "N/A"
        )
        typer.echo(
            f"  Weighted net     {fmt_money_short_signed(broker_detail.weighted_net_flow)} IDR   "
            f"Smart share  {smart_share}"
        )
        buyer_share = (
            f"{broker_detail.top_buyer_share_pct:.1f}%"
            if broker_detail.top_buyer_share_pct is not None else "N/A"
        )
        seller_share = (
            f"{broker_detail.top_seller_share_pct:.1f}%"
            if broker_detail.top_seller_share_pct is not None else "N/A"
        )
        typer.echo(
            f"  Concentration    top buyer {buyer_share}; top seller {seller_share}"
        )
        typer.echo(
            f"  Quality          {broker_detail.quality}; "
            f"{broker_detail.broker_weight_quality}"
        )

    # ── PRESET GATES ────────────────────────────────────────────────────────
    if preset_eval is not None:
        typer.echo("")
        section_header(
            f"PRESET — {preset_eval.name}",
            f"final: {style_classification(preset_eval.classification)}",
        )
        for gate in preset_eval.gates:
            typer.echo(
                f"  {style_gate(gate.passed):<14} "
                f"{gate.label:<15} actual={gate.actual:<10} required={gate.required}"
            )
        if preset_eval.passed:
            typer.echo(typer.style(
                "  Tested plan: TP +5%, SL -5%, max hold 10 trading days.",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        else:
            typer.echo(typer.style(
                f"  {format_failed_gates_summary(preset_eval)}",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        if broker_quality_note is not None:
            note_color = (
                typer.colors.YELLOW
                if broker_quality_note.level == "warning"
                else typer.colors.CYAN
            )
            typer.echo(typer.style(
                f"  {broker_quality_note.message}",
                fg=note_color,
            ))

    # ── MARKET REGIME ───────────────────────────────────────────────────────
    if market_regime is not None:
        typer.echo("")
        section_header("MARKET REGIME", market_regime.label)
        typer.echo(
            f"  Breadth SMA20  {fmt_pct(market_regime.breadth_above_sma20_pct)}   "
            f"5d change  {fmt_pct(market_regime.breadth_change_5d_pct, True)}"
        )
        typer.echo(
            f"  Benchmark 20d  {fmt_pct(market_regime.benchmark_return_20d_pct, True)}   "
            f"Foreign flow breadth  {fmt_pct(market_regime.foreign_flow_breadth_pct)}"
        )

    # ── RISK CONFIRMATION ────────────────────────────────────────────────────
    typer.echo("")
    if risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        section_header(
            "RISK CONFIRMATION",
            f"verdict: {style_risk(r.risk_level_name)}  conf: {r.confidence}/100",
        )
        typer.echo(
            f"  SMA20  {float(snap.sma):>10,.0f}   "
            f"EMA20  {float(snap.ema):>10,.0f}   "
            f"RSI14  {float(snap.rsi):>5.1f}"
        )
        for reason in r.rationale_list[:3]:
            typer.echo(typer.style(f"  · {reason}", fg=typer.colors.BRIGHT_BLACK))
    else:
        section_header("RISK CONFIRMATION")
        typer.echo(typer.style(
            "  Insufficient candle data for risk assessment.",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── STRATEGY RISK GATE ──────────────────────────────────────────────────
    if strategy_risk_level is not None:
        typer.echo("")
        _strat_color = {
            "LOW_RISK": typer.colors.GREEN,
            "HIGH_RISK": typer.colors.RED,
            "MODERATE": typer.colors.YELLOW,
        }.get(strategy_risk_level, typer.colors.WHITE)
        _strat_sym = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}.get(
            strategy_risk_level, "?"
        )
        section_header(
            f"STRATEGY GATE ({strategy_risk_name})",
            typer.style(f"{_strat_sym} {strategy_risk_level}", fg=_strat_color, bold=True),
        )
        if strategy_risk_level == "HIGH_RISK":
            typer.echo(typer.style(
                f"  ⚠ Strategy '{strategy_risk_name}' signals HIGH_RISK — "
                "overrides preset to AVOID.",
                fg=typer.colors.RED,
            ))
        elif strategy_risk_level == "LOW_RISK":
            typer.echo(typer.style(
                f"  ✓ Strategy '{strategy_risk_name}' confirms entry signal.",
                fg=typer.colors.GREEN,
            ))
        else:
            typer.echo(typer.style(
                f"  ~ Strategy '{strategy_risk_name}' is neutral — no override.",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── SIZING ───────────────────────────────────────────────────────────────
    show_sizing = capital is not None and not (
        preset_eval is not None and not preset_eval.passed
    )
    if show_sizing:
        typer.echo("")
        if preset_sizing and preset_sizing.lots > 0:
            section_header("PRESET SIZING")
            typer.echo(
                f"  Entry   {float(preset_sizing.entry_price):>10,.0f}   "
                f"Stop  {float(preset_sizing.stop_price):>10,.0f}  "
                f"({float(preset_sizing.stop_pct):+.2f}%)   "
                f"Target  {float(preset_sizing.target_price):>10,.0f}  "
                f"({float(preset_sizing.target_pct):+.2f}%)"
            )
            actual_risk = Decimal(str(preset_sizing.shares)) * preset_sizing.stop_distance
            typer.echo(
                f"  Position  {preset_sizing.lots} lots = "
                f"{preset_sizing.shares:,} shares   "
                f"Cost  {float(preset_sizing.position_cost):,.0f} IDR  "
                f"({float(preset_sizing.capital_used_pct):.1f}% of capital)"
            )
            typer.echo(
                f"  Risk    {float(actual_risk):>12,.0f} IDR   "
                f"Max hold  {config.foreign_bounce_max_hold_days} trading days"
            )
            if atr_value is not None and atr_value > 0:
                stop_to_atr = preset_sizing.stop_distance / atr_value
                note = f"5% stop = {float(stop_to_atr):.2f}× ATR14"
                if stop_to_atr < Decimal("1"):
                    note += " (tight vs daily volatility)"
                typer.echo(typer.style(f"  ({note})", fg=typer.colors.BRIGHT_BLACK))
        elif preset_sizing and preset_sizing.lots == 0:
            section_header("PRESET SIZING")
            typer.echo(typer.style(
                "  INSUFFICIENT CAPITAL: cannot fill 1 lot with 5% stop sizing.",
                fg=typer.colors.RED,
            ))
        elif sizing and sizing.lots > 0:
            section_header("SIZING")
            typer.echo(
                f"  Entry   {float(sizing.entry_price):>10,.0f}   "
                f"Stop  {float(sizing.stop_price):>10,.0f}  ({float(sizing.stop_pct):+.2f}%)   "
                f"Target  {float(sizing.target_price):>10,.0f}  ({float(sizing.target_pct):+.2f}%)"
            )
            actual_risk = Decimal(str(sizing.shares)) * sizing.stop_distance
            actual_reward = actual_risk * sizing.reward_risk_ratio
            typer.echo(
                f"  Position  {sizing.lots} lots = {sizing.shares:,} shares   "
                f"Cost  {float(sizing.position_cost):,.0f} IDR  "
                f"({float(sizing.capital_used_pct):.1f}% of capital)"
            )
            typer.echo(
                f"  Risk    {float(actual_risk):>12,.0f} IDR   "
                f"Reward  {float(actual_reward):>12,.0f} IDR"
            )
            typer.echo(typer.style(
                f"  (ATR14={float(atr_value):.0f} · stop={float(sizing.atr_multiplier):.1f}×ATR"
                f" · RR={float(sizing.reward_risk_ratio):.1f})",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        elif sizing and sizing.lots == 0:
            section_header("SIZING")
            typer.echo(typer.style(
                "  INSUFFICIENT CAPITAL: cannot fill 1 lot at this position size.",
                fg=typer.colors.RED,
            ))
            typer.echo(typer.style(
                f"  (Need ≥ {sizing.shares + 100} shares × {float(sizing.entry_price):,.0f} = "
                f"{float((Decimal(str(sizing.shares + 100)) * sizing.entry_price)):,.0f} IDR)",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        else:
            section_header("SIZING")
            typer.echo(typer.style(
                "  Cannot size position — ATR unavailable.",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── HISTORY ──────────────────────────────────────────────────────────────
    typer.echo("")
    if backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        section_header(
            "HISTORY",
            f"({strategy_name})  {r.trade_count} trades",
        )
        typer.echo(
            f"  Win rate  {style_winrate(r.win_rate)}   "
            f"Profit factor  {float(r.profit_factor):.2f}   "
            f"Max DD  {float(r.max_drawdown_pct):.1f}%"
        )
        if r.avg_win and r.avg_loss:
            typer.echo(
                f"  Avg win  {float(r.avg_win):>12,.0f} IDR   "
                f"Avg loss  {float(r.avg_loss):>12,.0f} IDR"
            )
    elif backtest_result is not None and backtest_result.trade_count == 0:
        section_header("HISTORY", f"({strategy_name})")
        typer.echo(typer.style(
            "  No trades triggered in available history (needs more broker data).",
            fg=typer.colors.BRIGHT_BLACK,
        ))
        typer.echo(typer.style(
            f"  Tip: saham backtest {ticker} --strategy {strategy_name} --verbose",
            fg=typer.colors.BRIGHT_BLACK,
        ))
    elif not no_backtest:
        section_header("HISTORY")
        typer.echo(typer.style(
            f"  Could not run backtest. Run: saham fetch market {ticker} --days 730",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── SENTIMENT ────────────────────────────────────────────────────────────
    if not no_sentiment:
        typer.echo("")
        if sentiment_resp and not sentiment_resp.warning:
            snap = sentiment_resp.snapshot
            call = snap.overall_sentiment.value.upper()
            section_header(
                "SENTIMENT (3d)",
                f"call: {style_sentiment_call(call)}",
            )
            typer.echo(
                f"  {snap.total_count} headlines   "
                f"(+{snap.positive_count} / ={snap.neutral_count} / -{snap.negative_count})   "
                f"confidence  {snap.confidence_pct}%"
            )
        else:
            section_header("SENTIMENT (3d)")
            message = sentiment_warning or "News unavailable (no network or fetch failed)."
            typer.echo(typer.style(
                f"  {message}",
                fg=typer.colors.BRIGHT_BLACK,
            ))
            if not sentiment_verbose:
                typer.echo(typer.style(
                    "  Use --sentiment-verbose to show provider details.",
                    fg=typer.colors.BRIGHT_BLACK,
                ))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    typer.echo("")
    sep("=")
    summary_parts = swing_summary_parts(accum, risk_resp, backtest_result, sentiment_resp)

    if summary_parts:
        typer.echo("SUMMARY: " + typer.style(" · ".join(summary_parts), bold=True))
    else:
        typer.echo("SUMMARY: insufficient data for assessment")

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
    typer.echo(typer.style(f"PLAN:  {plan_text}", fg=plan_style, bold=plan_style in {"green", "red"}))

    sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")
