"""
CLI commands for swing trade composite analysis and position sizing.

Commands:
  saham swing TICKER   — unified 5-section composite view
  saham size  TICKER   — ATR-based position sizing calculator

Each section in `swing` calls an existing use case and degrades
gracefully when data is unavailable, so the command is always useful.

Layer: Adapter
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.rules.exceptions import StrategyNotFoundError
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_risk import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.backtest import BacktestRequest, BacktestUseCase
from src.application.use_case.fetch_sentiment import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.application.use_case.swing_backtest import (
    FOREIGN_BOUNCE_PRESET as BACKTEST_FOREIGN_BOUNCE_PRESET,
)
from src.application.use_case.swing_backtest import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory

DEFAULT_DB_PATH = Path("data.db")
_W = 70  # display width

FOREIGN_BOUNCE_PRESET = "foreign-bounce"
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")
FOREIGN_BOUNCE_MAX_HOLD_DAYS = 10


@dataclass(frozen=True)
class PresetGate:
    label: str
    passed: bool
    actual: str
    required: str


@dataclass(frozen=True)
class PresetEvaluation:
    name: str
    passed: bool
    classification: str
    gates: tuple[PresetGate, ...]
    failed_reasons: tuple[str, ...]


# ─── formatting helpers ──────────────────────────────────────────────────────

def _style_risk(level: str) -> str:
    if level == "LOW_RISK":
        return typer.style(level, fg=typer.colors.GREEN, bold=True)
    if level == "HIGH_RISK":
        return typer.style(level, fg=typer.colors.RED, bold=True)
    return typer.style(level, fg=typer.colors.YELLOW, bold=True)


def _style_trend(trend: str) -> str:
    if trend == "UP":
        return typer.style(trend, fg=typer.colors.GREEN)
    if trend == "DOWN":
        return typer.style(trend, fg=typer.colors.RED)
    return typer.style(trend, fg=typer.colors.YELLOW)


def _style_sentiment_call(call: str) -> str:
    if call == "POSITIVE":
        return typer.style(call, fg=typer.colors.GREEN, bold=True)
    if call == "NEGATIVE":
        return typer.style(call, fg=typer.colors.RED, bold=True)
    return typer.style(call, fg=typer.colors.YELLOW, bold=True)


def _style_score(s: float) -> str:
    if s >= 70:
        return typer.style(f"{s:.1f}", fg=typer.colors.GREEN, bold=True)
    if s >= 40:
        return typer.style(f"{s:.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:.1f}", fg=typer.colors.WHITE)


def _style_bb(pctile: float) -> str:
    pct_int = int(pctile * 100)
    if pctile <= 0.20:
        return typer.style(f"{pct_int}%", fg=typer.colors.GREEN)
    if pctile <= 0.40:
        return typer.style(f"{pct_int}%", fg=typer.colors.YELLOW)
    return f"{pct_int}%"


def _style_winrate(wr: Decimal) -> str:
    v = float(wr)
    if v >= 55:
        return typer.style(f"{v:.1f}%", fg=typer.colors.GREEN)
    if v >= 45:
        return typer.style(f"{v:.1f}%", fg=typer.colors.YELLOW)
    return typer.style(f"{v:.1f}%", fg=typer.colors.RED)


def _sep(char: str = "=") -> None:
    typer.echo(char * _W)


def _section_header(title: str, right: str = "") -> None:
    styled = typer.style(title, bold=True)
    if right:
        gap = max(1, _W - len(title) - len(right) - 2)
        typer.echo(f"{styled}{' ' * gap}{right}")
    else:
        typer.echo(styled)


def _signal_label(c: AccumulationCandidate) -> str:
    if c.bb_width_pctile is not None and c.bb_width_pctile <= 0.20 and c.score >= 60:
        return "coiled spring"
    if c.score >= 70 and c.consecutive_streak >= 8:
        return "strong"
    if c.score >= 60 and c.consecutive_streak >= 5:
        return "building"
    if c.score >= 70:
        return "high score"
    if c.score >= 40:
        return "moderate"
    return "weak"


def _fmt_optional_float(value: float | None, suffix: str = "") -> str:
    return "missing" if value is None else f"{value:.1f}{suffix}"


def _evaluate_foreign_bounce(
    accum: AccumulationCandidate | None,
) -> PresetEvaluation:
    """Evaluate audited foreign-bounce gates for one accumulation candidate."""
    if accum is None:
        return PresetEvaluation(
            name=FOREIGN_BOUNCE_PRESET,
            passed=False,
            classification="AVOID",
            gates=(
                PresetGate(
                    label="broker flow data",
                    passed=False,
                    actual="missing",
                    required="available",
                ),
            ),
            failed_reasons=("No accumulation/broker-flow candidate available",),
        )

    gates = (
        PresetGate(
            label="score",
            passed=accum.score >= 70,
            actual=f"{accum.score:.1f}",
            required=">= 70",
        ),
        PresetGate(
            label="vwap_disc_pct",
            passed=accum.vwap_discount_pct is not None and accum.vwap_discount_pct >= 3,
            actual=_fmt_optional_float(accum.vwap_discount_pct, "%"),
            required=">= +3%",
        ),
        PresetGate(
            label="trend",
            passed=accum.trend == "SIDE",
            actual=accum.trend,
            required="SIDE",
        ),
        PresetGate(
            label="flow_pct",
            passed=accum.avg_flow_ratio is not None and accum.avg_flow_ratio >= 5,
            actual=_fmt_optional_float(accum.avg_flow_ratio, "%"),
            required=">= +5%",
        ),
        PresetGate(
            label="RSI present",
            passed=accum.rsi is not None,
            actual=_fmt_optional_float(accum.rsi),
            required="present",
        ),
        PresetGate(
            label="RSI",
            passed=accum.rsi is not None and accum.rsi <= 60,
            actual=_fmt_optional_float(accum.rsi),
            required="<= 60",
        ),
    )
    failed = tuple(
        f"{gate.label}: {gate.actual} (required {gate.required})"
        for gate in gates
        if not gate.passed
    )
    passed = not failed
    if passed:
        classification = "ENTER"
    elif accum.score >= 70 or len(failed) <= 2:
        classification = "WATCH"
    else:
        classification = "AVOID"

    return PresetEvaluation(
        name=FOREIGN_BOUNCE_PRESET,
        passed=passed,
        classification=classification,
        gates=gates,
        failed_reasons=failed,
    )


def _style_gate(passed: bool) -> str:
    label = "PASS" if passed else "FAIL"
    color = typer.colors.GREEN if passed else typer.colors.RED
    return typer.style(label, fg=color, bold=True)


def _style_classification(value: str) -> str:
    if value == "ENTER":
        return typer.style(value, fg=typer.colors.GREEN, bold=True)
    if value == "WATCH":
        return typer.style(value, fg=typer.colors.YELLOW, bold=True)
    return typer.style(value, fg=typer.colors.RED, bold=True)


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def _parse_regime_filter(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    regimes = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    valid = {"BULLISH", "SIDEWAYS", "WEAK", "RISK_OFF"}
    invalid = [regime for regime in regimes if regime not in valid]
    if invalid:
        raise typer.BadParameter(
            "--allow-regimes must contain only: BULLISH, SIDEWAYS, WEAK, RISK_OFF"
        )
    return regimes


def _display_swing_backtest(response: SwingBacktestResponse, show_trades: int) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(typer.style("WALK-FORWARD SWING BACKTEST", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(
        f"Preset: {response.preset} | Period: {response.start_date} to {response.end_date}"
    )
    typer.echo(
        "Read as: the workflow scans each replay date, opens eligible signals within "
        "portfolio limits, then exits by TP/SL/max-hold."
    )
    typer.echo("")
    typer.echo(f"{'METRIC':<24} {'VALUE':>18}")
    typer.echo("-" * 46)
    typer.echo(f"{'Initial capital':<24} {float(response.initial_capital):>18,.0f}")
    typer.echo(f"{'Final equity':<24} {float(response.final_equity):>18,.0f}")
    typer.echo(f"{'Total return':<24} {_fmt_pct(response.total_return_pct, True):>18}")
    typer.echo(f"{'Max drawdown':<24} {_fmt_pct(response.max_drawdown_pct, True):>18}")
    typer.echo(f"{'Trades':<24} {response.trade_count:>18}")
    typer.echo(f"{'Win rate':<24} {_fmt_pct(response.win_rate_pct):>18}")
    typer.echo(f"{'Avg trade return':<24} {_fmt_pct(response.avg_trade_return_pct, True):>18}")
    profit_factor = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    typer.echo(f"{'Profit factor':<24} {profit_factor:>18}")
    typer.echo(f"{'Exposure days':<24} {_fmt_pct(response.exposure_pct):>18}")
    typer.echo("")
    typer.echo(
        f"Skipped: no_cash={response.skipped_no_cash}, "
        f"duplicate={response.skipped_duplicate}, "
        f"no_forward_data={response.skipped_no_forward_data}, "
        f"regime={response.skipped_by_regime}"
    )

    if response.regime_stats:
        typer.echo("")
        typer.echo("PERFORMANCE BY ENTRY REGIME")
        typer.echo("-" * 86)
        typer.echo(
            f"{'REGIME':<12} {'TRADES':>8} {'AVG_RET':>10} "
            f"{'WIN':>8} {'TOTAL_PNL':>16}"
        )
        for stat in response.regime_stats:
            typer.echo(
                f"{stat.regime:<12} {stat.count:>8} "
                f"{_fmt_pct(stat.avg_return_pct, True):>10} "
                f"{_fmt_pct(stat.win_rate_pct):>8} "
                f"{float(stat.total_pnl):>16,.0f}"
            )

    if show_trades > 0 and response.trades:
        typer.echo("")
        typer.echo("RECENT TRADES")
        typer.echo("-" * 86)
        typer.echo(
            f"{'ENTRY':<10} {'EXIT':<10} {'TICKER':<7} {'LOTS':>6} "
            f"{'RET':>9} {'PNL':>14} {'DAYS':>5} {'REASON':<10}"
        )
        for trade in response.trades[-show_trades:]:
            typer.echo(
                f"{trade.entry_date:%Y-%m-%d} {trade.exit_date:%Y-%m-%d} "
                f"{trade.ticker:<7} {trade.lots:>6} "
                f"{_fmt_pct(trade.net_return_pct, True):>9} "
                f"{float(trade.pnl):>14,.0f} {trade.holding_days:>5} "
                f"{trade.exit_reason:<10}"
            )

    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")

    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))


def _display_regime(response: MarketRegimeResponse) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(typer.style("MARKET REGIME", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(f"Date: {response.as_of_date} | Label: {response.label} | Score: {response.score}/7")
    typer.echo("")
    typer.echo(f"{'METRIC':<30} {'VALUE':>16}")
    typer.echo("-" * 48)
    close = "N/A" if response.benchmark_close is None else f"{float(response.benchmark_close):,.2f}"
    sma20 = "N/A" if response.benchmark_sma20 is None else f"{float(response.benchmark_sma20):,.2f}"
    sma50 = "N/A" if response.benchmark_sma50 is None else f"{float(response.benchmark_sma50):,.2f}"
    typer.echo(f"{response.benchmark_ticker + ' close':<30} {close:>16}")
    typer.echo(f"{'Benchmark SMA20':<30} {sma20:>16}")
    typer.echo(f"{'Benchmark SMA50':<30} {sma50:>16}")
    typer.echo(
        f"{'Benchmark 5d return':<30} "
        f"{_fmt_pct(response.benchmark_return_5d_pct, True):>16}"
    )
    typer.echo(
        f"{'Benchmark 20d return':<30} "
        f"{_fmt_pct(response.benchmark_return_20d_pct, True):>16}"
    )
    typer.echo(f"{'Breadth above SMA20':<30} {_fmt_pct(response.breadth_above_sma20_pct):>16}")
    typer.echo(f"{'Breadth change 5d':<30} {_fmt_pct(response.breadth_change_5d_pct, True):>16}")
    typer.echo(f"{'Foreign flow breadth':<30} {_fmt_pct(response.foreign_flow_breadth_pct):>16}")
    typer.echo(f"{'Universe evaluated':<30} {response.breadth_count:>16}/{response.universe_count}")
    typer.echo(
        f"{'Flow evaluated':<30} "
        f"{response.foreign_flow_count:>16}/{response.universe_count}"
    )
    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))


def _print_swing_output(
    ticker: str,
    today: date,
    profile: str,
    strategy_name: str,
    window: int,
    accum: "AccumulationCandidate | None",
    risk_resp,
    atr_value: "Decimal | None",
    sizing: "SizingResult | None",
    preset_eval: "PresetEvaluation | None",
    preset_sizing: "PercentSizingResult | None",
    market_regime: "MarketRegimeResponse | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    no_backtest: bool,
    no_sentiment: bool,
) -> None:
    typer.echo("")
    _sep("=")
    typer.echo(typer.style(
        f"SWING VIEW — {ticker} · {today} · profile={profile}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    _sep("=")

    # ── ACCUMULATION ─────────────────────────────────────────────────────────
    typer.echo("")
    if accum:
        label = _signal_label(accum)
        _section_header(
            f"ACCUMULATION ({window}d)",
            f"signal: {typer.style(label, bold=label in ('strong', 'coiled spring'))}",
        )
        flow_str = (
            f"{accum.avg_flow_ratio:+.1f}%"
            if accum.avg_flow_ratio is not None else "—"
        )
        vwap_str = (
            f"{accum.vwap_discount_pct:+.1f}%"
            if accum.vwap_discount_pct is not None else "—"
        )
        bb_str = _style_bb(accum.bb_width_pctile) if accum.bb_width_pctile is not None else "—"
        net_str = f"{accum.net_buy_days}/{accum.total_days}"

        typer.echo(
            f"  Score  {_style_score(accum.score)}   "
            f"STREAK  {accum.consecutive_streak}d   "
            f"NET_DAYS  {net_str}   "
            f"FLOW%  {flow_str}"
        )
        typer.echo(
            f"  VWAP   {vwap_str}    "
            f"BB%ILE  {bb_str}    "
            f"TREND  {_style_trend(accum.trend)}"
        )
        if accum.score_breakdown:
            bd = accum.score_breakdown
            typer.echo(typer.style(
                f"  [cons={bd.get('cons',0):.1f} streak={bd.get('streak',0):.1f}"
                f" vwap={bd.get('vwap',0):.1f} rsi={bd.get('rsi',0):.1f}"
                f" flow={bd.get('flow',0):.1f} bb={bd.get('bb',0):.1f}]",
                fg=typer.colors.BRIGHT_BLACK,
            ))
    else:
        _section_header(f"ACCUMULATION ({window}d)")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham broker fetch {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── PRESET GATES ────────────────────────────────────────────────────────
    if preset_eval is not None:
        typer.echo("")
        _section_header(
            f"PRESET — {preset_eval.name}",
            f"final: {_style_classification(preset_eval.classification)}",
        )
        for gate in preset_eval.gates:
            typer.echo(
                f"  {_style_gate(gate.passed):<14} "
                f"{gate.label:<15} actual={gate.actual:<10} required={gate.required}"
            )
        if preset_eval.passed:
            typer.echo(typer.style(
                "  Tested plan: TP +5%, SL -5%, max hold 10 trading days.",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        else:
            typer.echo(typer.style(
                "  Failed gates: " + "; ".join(preset_eval.failed_reasons[:3]),
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── MARKET REGIME ───────────────────────────────────────────────────────
    if market_regime is not None:
        typer.echo("")
        _section_header("MARKET REGIME", market_regime.label)
        typer.echo(
            f"  Breadth SMA20  {_fmt_pct(market_regime.breadth_above_sma20_pct)}   "
            f"5d change  {_fmt_pct(market_regime.breadth_change_5d_pct, True)}"
        )
        typer.echo(
            f"  Benchmark 20d  {_fmt_pct(market_regime.benchmark_return_20d_pct, True)}   "
            f"Foreign flow breadth  {_fmt_pct(market_regime.foreign_flow_breadth_pct)}"
        )

    # ── RISK CONFIRMATION ────────────────────────────────────────────────────
    typer.echo("")
    if risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        _section_header(
            "RISK CONFIRMATION",
            f"verdict: {_style_risk(r.risk_level_name)}  conf: {r.confidence}/100",
        )
        typer.echo(
            f"  SMA20  {float(snap.sma):>10,.0f}   "
            f"EMA20  {float(snap.ema):>10,.0f}   "
            f"RSI14  {float(snap.rsi):>5.1f}"
        )
        for reason in r.rationale_list[:3]:
            typer.echo(typer.style(f"  · {reason}", fg=typer.colors.BRIGHT_BLACK))
    else:
        _section_header("RISK CONFIRMATION")
        typer.echo(typer.style(
            "  Insufficient candle data for risk assessment.",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── SIZING ───────────────────────────────────────────────────────────────
    show_sizing = capital is not None and not (
        preset_eval is not None and not preset_eval.passed
    )
    if show_sizing:
        typer.echo("")
        if preset_sizing and preset_sizing.lots > 0:
            _section_header("PRESET SIZING")
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
                f"Max hold  {FOREIGN_BOUNCE_MAX_HOLD_DAYS} trading days"
            )
            if atr_value is not None and atr_value > 0:
                stop_to_atr = preset_sizing.stop_distance / atr_value
                note = f"5% stop = {float(stop_to_atr):.2f}× ATR14"
                if stop_to_atr < Decimal("1"):
                    note += " (tight vs daily volatility)"
                typer.echo(typer.style(f"  ({note})", fg=typer.colors.BRIGHT_BLACK))
        elif preset_sizing and preset_sizing.lots == 0:
            _section_header("PRESET SIZING")
            typer.echo(typer.style(
                "  INSUFFICIENT CAPITAL: cannot fill 1 lot with 5% stop sizing.",
                fg=typer.colors.RED,
            ))
        elif sizing and sizing.lots > 0:
            _section_header("SIZING")
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
            _section_header("SIZING")
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
            _section_header("SIZING")
            typer.echo(typer.style(
                "  Cannot size position — ATR unavailable.",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── HISTORY ──────────────────────────────────────────────────────────────
    typer.echo("")
    if backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        _section_header(
            "HISTORY",
            f"({strategy_name})  {r.trade_count} trades",
        )
        typer.echo(
            f"  Win rate  {_style_winrate(r.win_rate)}   "
            f"Profit factor  {float(r.profit_factor):.2f}   "
            f"Max DD  {float(r.max_drawdown_pct):.1f}%"
        )
        if r.avg_win and r.avg_loss:
            typer.echo(
                f"  Avg win  {float(r.avg_win):>12,.0f} IDR   "
                f"Avg loss  {float(r.avg_loss):>12,.0f} IDR"
            )
    elif backtest_result is not None and backtest_result.trade_count == 0:
        _section_header("HISTORY", f"({strategy_name})")
        typer.echo(typer.style(
            "  No trades triggered in available history (needs more broker data).",
            fg=typer.colors.BRIGHT_BLACK,
        ))
        typer.echo(typer.style(
            f"  Tip: saham backtest {ticker} --strategy {strategy_name} --verbose",
            fg=typer.colors.BRIGHT_BLACK,
        ))
    elif not no_backtest:
        _section_header("HISTORY")
        typer.echo(typer.style(
            f"  Could not run backtest. Run: saham fetch {ticker} --days 730",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── SENTIMENT ────────────────────────────────────────────────────────────
    if not no_sentiment:
        typer.echo("")
        if sentiment_resp and not sentiment_resp.warning:
            snap = sentiment_resp.snapshot
            call = snap.overall_sentiment.value.upper()
            _section_header(
                "SENTIMENT (3d)",
                f"call: {_style_sentiment_call(call)}",
            )
            typer.echo(
                f"  {snap.total_count} headlines   "
                f"(+{snap.positive_count} / ={snap.neutral_count} / -{snap.negative_count})   "
                f"confidence  {snap.confidence_pct}%"
            )
        else:
            _section_header("SENTIMENT (3d)")
            typer.echo(typer.style(
                "  News unavailable (no network or fetch failed).",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    typer.echo("")
    _sep("=")
    summary_parts = []
    if accum:
        summary_parts.append(f"Score {accum.score:.1f}")
    if risk_resp:
        summary_parts.append(risk_resp.assessment.risk_level_name)
    if backtest_result and backtest_result.trade_count > 0:
        summary_parts.append(f"{float(backtest_result.win_rate):.0f}% WR")
    if sentiment_resp and not sentiment_resp.warning:
        summary_parts.append(
            sentiment_resp.snapshot.overall_sentiment.value.lower() + " news"
        )

    if summary_parts:
        typer.echo("SUMMARY: " + typer.style(" · ".join(summary_parts), bold=True))
    else:
        typer.echo("SUMMARY: insufficient data for assessment")

    if preset_eval is not None:
        if preset_eval.passed and preset_sizing and preset_sizing.lots > 0:
            typer.echo(
                f"PLAN:  ENTER setup passed. Consider {preset_sizing.lots} lots at "
                f"{float(preset_sizing.entry_price):,.0f}; TP "
                f"{float(preset_sizing.target_price):,.0f}; SL "
                f"{float(preset_sizing.stop_price):,.0f}; max hold "
                f"{FOREIGN_BOUNCE_MAX_HOLD_DAYS} trading days."
            )
        elif preset_eval.passed:
            typer.echo("PLAN:  ENTER setup passed. Add --capital to compute lot size.")
        elif preset_eval.classification == "WATCH":
            typer.echo(
                "PLAN:  WATCH only. Preset is close but not fully confirmed; "
                "wait for failed gates to improve."
            )
        else:
            typer.echo("PLAN:  AVOID. Preset gates are not aligned.")
    elif sizing and sizing.lots > 0:
        typer.echo(
            f"PLAN:  Sized scenario: {sizing.lots} lots at {float(sizing.entry_price):,.0f}.  "
            f"Stop {float(sizing.stop_price):,.0f}.  "
            f"Target {float(sizing.target_price):,.0f}."
        )
    elif sizing and sizing.lots == 0:
        typer.echo("PLAN:  Position too small for 1 lot — reduce entry or increase capital.")
    elif capital and not atr_value:
        typer.echo("PLAN:  Fetch more data to enable position sizing (run saham fetch --days 90).")

    _sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")


# ─── swing command ───────────────────────────────────────────────────────────

def swing(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="Risk profile: balanced/conservative/aggressive"),
    ] = "balanced",
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            "-S",
            help="Backtest strategy name (default: foreign-accumulation)",
        ),
    ] = "foreign-accumulation",
    preset: Annotated[
        Optional[str],
        typer.Option("--preset", help="Swing preset: foreign-bounce"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation analysis window in days (default: 7)"),
    ] = 7,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Capital in IDR — enables position sizing block"),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade (default: 1.0)"),
    ] = 1.0,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance (default: 1.5)"),
    ] = 1.5,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target (default: 2.0)"),
    ] = 2.0,
    no_sentiment: Annotated[
        bool,
        typer.Option("--no-sentiment", help="Skip news sentiment (offline mode)"),
    ] = False,
    no_backtest: Annotated[
        bool,
        typer.Option("--no-backtest", help="Skip historical backtest"),
    ] = False,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Add market regime context"),
    ] = False,
    regime_universe: Annotated[
        str,
        typer.Option("--regime-universe", help="Universe for breadth context"),
    ] = "idx80",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Unified composite swing trade analysis for a single stock.

    Combines: accumulation signal, risk confirmation, position sizing,
    historical backtest, and news sentiment in one command.

    Replaces the 5–6 command morning workflow:
      saham screen accumulation, saham risk, saham compute ATR,
      saham backtest, saham sentiment — all in one.

    Examples:
        saham swing BBRI
        saham swing BBRI --preset foreign-bounce --capital 10000000
        saham swing BBRI --capital 10000000 --risk-pct 1
        saham swing BBRI --profile conservative --no-sentiment
        saham swing BBRI --no-backtest --no-sentiment
        saham swing BBRI --capital 10000000 --entry 4825 --rr 2.5
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    preset_name = preset.lower() if preset else None
    if preset_name is not None and preset_name != FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. Available presets: {FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry()

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch {ticker_upper}", err=True
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # ── Accumulation ─────────────────────────────────────────────────────────
    accum_candidate: AccumulationCandidate | None = None
    try:
        accum_uc = AccumulationScreenUseCase(
            broker_repository=broker_repo,
            market_repository=market_repo,
        )
        accum_resp = accum_uc.execute(AccumulationScreenRequest(
            tickers=[ticker_upper],
            window_days=window,
            min_net_buy_days=0,
            min_score=0.0,
        ))
        if accum_resp.candidates:
            accum_candidate = accum_resp.candidates[0]
    except Exception:
        pass

    # ── Risk ─────────────────────────────────────────────────────────────────
    risk_resp = None
    try:
        risk_uc = AssessRiskUseCase(repository=market_repo, registry=registry)
        risk_resp = risk_uc.execute(AssessRiskRequest(
            ticker=ticker_upper,
            profile=profile,
        ))
    except Exception:
        pass

    # ── ATR ──────────────────────────────────────────────────────────────────
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, 14)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception:
        pass

    # ── Position sizing ───────────────────────────────────────────────────────
    sizing: SizingResult | None = None
    preset_eval: PresetEvaluation | None = None
    preset_sizing: PercentSizingResult | None = None
    if preset_name == FOREIGN_BOUNCE_PRESET:
        preset_eval = _evaluate_foreign_bounce(accum_candidate)

    if capital is not None and preset_eval is not None and preset_eval.passed:
        try:
            entry_dec = Decimal(str(entry_price)) if entry_price else latest_close
            preset_sizing = compute_percent_position_size(
                entry=entry_dec,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                stop_loss_pct=FOREIGN_BOUNCE_STOP_LOSS,
                take_profit_pct=FOREIGN_BOUNCE_TAKE_PROFIT,
            )
        except ValueError:
            pass
    elif capital is not None and atr_value and preset_eval is None:
        try:
            entry_dec = Decimal(str(entry_price)) if entry_price else latest_close
            sizing = compute_position_size(
                entry=entry_dec,
                atr=atr_value,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                atr_multiplier=Decimal(str(atr_mult)),
                reward_risk=Decimal(str(rr)),
            )
        except ValueError:
            pass

    # ── Backtest ─────────────────────────────────────────────────────────────
    backtest_result = None
    if not no_backtest:
        try:
            loader = StrategyLoader(registry=registry)
            rules_path = loader.resolve(strategy)
            bt_uc = BacktestUseCase(repository=market_repo, registry=registry)
            bt_resp = bt_uc.execute(BacktestRequest(
                ticker=ticker_upper,
                rules_file=rules_path,
                initial_capital=Decimal("100000000"),
            ))
            backtest_result = bt_resp.result
        except (StrategyNotFoundError, Exception):
            pass

    # ── Sentiment ─────────────────────────────────────────────────────────────
    sentiment_resp = None
    if not no_sentiment:
        try:
            news_provider = SentimentFactory.create_news_provider()
            classifier = SentimentFactory.create_classifier(use_ai=False)
            sent_uc = FetchSentimentUseCase(
                news_provider=news_provider,
                classifier=classifier,
            )
            sentiment_resp = sent_uc.execute(FetchSentimentRequest(
                ticker=ticker_upper,
                max_headlines=20,
                days=3,
            ))
        except Exception:
            pass

    # ── Market regime ───────────────────────────────────────────────────────
    market_regime: MarketRegimeResponse | None = None
    if with_regime:
        try:
            regime_tickers = resolve_tickers(
                universe=regime_universe,
                explicit=[],
                db_path=resolved_db,
            )
            regime_uc = MarketRegimeUseCase(
                market_repository=market_repo,
                broker_repository=broker_repo,
            )
            market_regime = regime_uc.execute(MarketRegimeRequest(
                universe=regime_tickers,
                benchmark_ticker=benchmark,
                as_of_date=today,
            ))
        except Exception:
            pass

    if output_format == "json":
        out: dict = {
            "ticker": ticker_upper,
            "date": str(today),
            "profile": profile,
            "accumulation": {
                "score": accum_candidate.score if accum_candidate else None,
                "streak": accum_candidate.consecutive_streak if accum_candidate else None,
                "trend": accum_candidate.trend if accum_candidate else None,
                "flow_pct": accum_candidate.avg_flow_ratio if accum_candidate else None,
                "vwap_disc_pct": accum_candidate.vwap_discount_pct if accum_candidate else None,
                "bb_width_pctile": accum_candidate.bb_width_pctile if accum_candidate else None,
            },
            "preset": {
                "name": preset_eval.name if preset_eval else None,
                "passed": preset_eval.passed if preset_eval else None,
                "classification": preset_eval.classification if preset_eval else None,
                "failed_reasons": list(preset_eval.failed_reasons) if preset_eval else [],
                "plan": {
                    "take_profit_pct": float(FOREIGN_BOUNCE_TAKE_PROFIT)
                    if preset_eval else None,
                    "stop_loss_pct": float(FOREIGN_BOUNCE_STOP_LOSS)
                    if preset_eval else None,
                    "max_hold_days": FOREIGN_BOUNCE_MAX_HOLD_DAYS
                    if preset_eval else None,
                },
            },
            "risk": {
                "level": risk_resp.assessment.risk_level_name if risk_resp else None,
                "confidence": risk_resp.assessment.confidence if risk_resp else None,
                "sma20": float(risk_resp.assessment.indicators.sma) if risk_resp else None,
                "ema20": float(risk_resp.assessment.indicators.ema) if risk_resp else None,
                "rsi14": float(risk_resp.assessment.indicators.rsi) if risk_resp else None,
            },
            "sizing": {
                "entry": float(
                    preset_sizing.entry_price if preset_sizing
                    else sizing.entry_price
                ) if (preset_sizing or sizing) else None,
                "stop": float(
                    preset_sizing.stop_price if preset_sizing
                    else sizing.stop_price
                ) if (preset_sizing or sizing) else None,
                "target": float(
                    preset_sizing.target_price if preset_sizing
                    else sizing.target_price
                ) if (preset_sizing or sizing) else None,
                "lots": (
                    preset_sizing.lots if preset_sizing
                    else sizing.lots if sizing else None
                ),
                "atr": float(atr_value) if atr_value else None,
            },
            "backtest": {
                "win_rate": float(backtest_result.win_rate) if backtest_result else None,
                "profit_factor": float(backtest_result.profit_factor) if backtest_result else None,
                "max_drawdown_pct": (
                    float(backtest_result.max_drawdown_pct)
                    if backtest_result else None
                ),
                "trade_count": backtest_result.trade_count if backtest_result else None,
            },
            "sentiment": {
                "call": (
                    sentiment_resp.snapshot.overall_sentiment.value
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "total_headlines": (
                    sentiment_resp.snapshot.total_count
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "confidence_pct": (
                    sentiment_resp.snapshot.confidence_pct
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
            },
            "market_regime": market_regime.to_dict() if market_regime else None,
        }
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    _print_swing_output(
        ticker=ticker_upper,
        today=today,
        profile=profile,
        strategy_name=strategy,
        window=window,
        accum=accum_candidate,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        preset_eval=preset_eval,
        preset_sizing=preset_sizing,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        no_backtest=no_backtest,
        no_sentiment=no_sentiment,
    )


# ─── swing backtest command ──────────────────────────────────────────────────

def swing_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = None,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_PRESET,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = 100_000_000,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = 1.0,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = 5,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = 5.0,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = 5.0,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = 10,
    cost_bps: Annotated[
        float,
        typer.Option("--cost-bps", help="One-way transaction cost in basis points", min=0),
    ] = 0.0,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group trades by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to print", min=0),
    ] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Walk-forward backtest for the deterministic swing workflow.

    This validates the full daily process: scan, apply preset gates, rank
    candidates, open only within portfolio limits, avoid duplicate positions,
    and exit by TP/SL/max-hold. It reads local cached market and broker data.
    """
    preset_name = preset.lower()
    if preset_name != BACKTEST_FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. "
            f"Available presets: {BACKTEST_FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        allowed_regimes = _parse_regime_filter(allow_regimes)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Backtesting {len(ticker_list)} tickers | {start_date} to {end_date} | "
        f"preset={preset_name} | max positions={max_positions}..."
    )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    try:
        response = use_case.execute(SwingBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            preset=preset_name,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_positions=max_positions,
            take_profit_pct=Decimal(str(take_profit)),
            stop_loss_pct=Decimal(str(stop_loss)),
            max_hold_days=max_hold,
            cost_bps=Decimal(str(cost_bps)),
            include_regime=with_regime or bool(allowed_regimes),
            benchmark_ticker=benchmark,
            allowed_regimes=allowed_regimes,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "preset": response.preset,
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "initial_capital": str(response.initial_capital),
            "final_equity": str(response.final_equity),
            "total_return_pct": response.total_return_pct,
            "max_drawdown_pct": response.max_drawdown_pct,
            "trade_count": response.trade_count,
            "win_rate_pct": response.win_rate_pct,
            "avg_trade_return_pct": response.avg_trade_return_pct,
            "profit_factor": response.profit_factor,
            "exposure_pct": response.exposure_pct,
            "skipped_no_cash": response.skipped_no_cash,
            "skipped_duplicate": response.skipped_duplicate,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "skipped_by_regime": response.skipped_by_regime,
            "warnings": response.warnings,
            "regime_stats": [stat.to_dict() for stat in response.regime_stats],
            "regime_by_date": {
                key.isoformat(): value.to_dict()
                for key, value in response.regime_by_date.items()
            },
            "trades": [trade.to_dict() for trade in response.trades],
            "equity_curve": [point.to_dict() for point in response.equity_curve],
        }, indent=2, default=str))
        return

    _display_swing_backtest(response, show_trades=show_trades)


def regime(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols for breadth context"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = "idx80",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker, e.g. ^JKSE"),
    ] = "^JKSE",
    as_of: Annotated[
        Optional[str],
        typer.Option("--as-of", help="Regime date, YYYY-MM-DD (default: today)"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Show deterministic IHSG market regime context for swing trading.

    Uses local cached benchmark candles, universe breadth, and broker flow data.
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        regime_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers for regime breadth. Specify --universe or ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    use_case = MarketRegimeUseCase(
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
        broker_repository=SQLiteBrokerRepository(resolved_db),
    )
    try:
        response = use_case.execute(MarketRegimeRequest(
            universe=ticker_list,
            benchmark_ticker=benchmark,
            as_of_date=regime_date,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, default=str))
        return

    _display_regime(response)


# ─── size command ─────────────────────────────────────────────────────────────

def size(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Total capital in IDR", min=1),
    ],
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade (default: 1.0)"),
    ] = 1.0,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance (default: 1.5)"),
    ] = 1.5,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target (default: 2.0)"),
    ] = 2.0,
    atr_period: Annotated[
        int,
        typer.Option("--atr-period", help="ATR period (default: 14)", min=2),
    ] = 14,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    ATR-based position sizing calculator for IDX swing trades.

    Computes stop price (1.5 × ATR below entry), target (2× risk/reward),
    and exact lot count from fixed-fractional capital risk.

    Examples:
        saham size BBRI --capital 10000000
        saham size BBRI --capital 10000000 --risk-pct 2 --entry 4825
        saham size BBRI --capital 50000000 --risk-pct 1 --rr 2.5
        saham size BBRI --capital 10000000 --atr-mult 2.0
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch {ticker_upper}", err=True
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # Compute ATR
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, atr_period)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception as e:
        typer.echo(f"Error computing ATR: {e}", err=True)
        raise typer.Exit(1)

    if not atr_value or atr_value <= 0:
        typer.echo(
            f"Cannot compute ATR({atr_period}) for {ticker_upper} — insufficient data.", err=True
        )
        typer.echo(f"Tip: Run: saham fetch {ticker_upper} --days 90", err=True)
        raise typer.Exit(1)

    entry_dec = Decimal(str(entry_price)) if entry_price else latest_close

    try:
        result = compute_position_size(
            entry=entry_dec,
            atr=atr_value,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            atr_multiplier=Decimal(str(atr_mult)),
            reward_risk=Decimal(str(rr)),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        out = {
            "ticker": ticker_upper,
            "date": str(today),
            "entry": float(result.entry_price),
            "atr": float(result.atr),
            "atr_period": atr_period,
            "atr_multiplier": float(result.atr_multiplier),
            "stop_price": float(result.stop_price),
            "stop_distance": float(result.stop_distance),
            "stop_pct": float(result.stop_pct),
            "target_price": float(result.target_price),
            "target_pct": float(result.target_pct),
            "reward_risk_ratio": float(result.reward_risk_ratio),
            "capital": float(result.capital),
            "risk_pct": risk_pct,
            "risk_amount": float(result.risk_amount),
            "reward_amount": float(result.reward_amount),
            "lots": result.lots,
            "shares": result.shares,
            "position_cost": float(result.position_cost),
            "capital_used_pct": float(result.capital_used_pct),
        }
        typer.echo(json.dumps(out, indent=2))
        return

    # ── Table output ──────────────────────────────────────────────────────────
    typer.echo("")
    _sep("=")
    typer.echo(typer.style(
        f"POSITION SIZE — {ticker_upper} · {today}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    _sep("=")

    typer.echo("")
    typer.echo(typer.style("INPUTS", bold=True))
    typer.echo(
        f"  Capital            {capital:>18,} IDR"
    )
    typer.echo(
        f"  Risk per trade     {risk_pct:>17.2f} %  =  {float(result.risk_amount):>12,.0f} IDR"
    )
    entry_src = "latest close" if not entry_price else "specified"
    typer.echo(
        f"  Entry ({entry_src})   {float(entry_dec):>18,.0f}"
    )
    typer.echo(
        f"  ATR({atr_period:>2})           {float(atr_value):>18.2f}"
    )
    typer.echo(
        f"  ATR multiplier     {float(result.atr_multiplier):>18.1f}×"
    )
    typer.echo(
        f"  Reward : Risk      {float(result.reward_risk_ratio):>18.1f}"
    )

    typer.echo("")
    typer.echo(typer.style("STOP", bold=True))
    typer.echo(
        f"  Stop price         {float(result.stop_price):>18,.0f}"
    )
    typer.echo(
        f"  Stop distance      {float(result.stop_distance):>18,.0f}  per share"
    )
    typer.echo(
        f"  Stop %             {float(result.stop_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("TARGET", bold=True))
    typer.echo(
        f"  Target price       {float(result.target_price):>18,.0f}"
    )
    typer.echo(
        f"  Target %           {float(result.target_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("POSITION", bold=True))
    if result.lots == 0:
        typer.echo(typer.style(
            f"  INSUFFICIENT CAPITAL — cannot fill 1 lot.\n"
            f"  Need at least {100 * float(entry_dec):,.0f} IDR for 1 lot "
            f"(stop = {float(result.stop_distance):.0f}/share).",
            fg=typer.colors.RED,
        ))
    else:
        typer.echo(
            f"  Raw shares         {int(result.risk_amount / result.stop_distance):>18}"
        )
        typer.echo(
            f"  Round lots         {result.lots:>18}  lots = {result.shares:,} shares"
        )
        typer.echo(
            f"  Position cost      {float(result.position_cost):>18,.0f}  IDR  "
            f"({float(result.capital_used_pct):.1f}% of capital)"
        )
        actual_risk = Decimal(str(result.shares)) * result.stop_distance
        actual_reward = actual_risk * result.reward_risk_ratio
        typer.echo(
            f"  Actual risk        {float(actual_risk):>18,.0f}  IDR  "
            f"(vs target {float(result.risk_amount):,.0f})"
        )
        typer.echo(
            f"  Actual reward      {float(actual_reward):>18,.0f}  IDR"
        )

    typer.echo("")
    _sep("=")
    if result.lots > 0:
        typer.echo(typer.style(
            f"ACTION: Buy {result.lots} lots at {float(entry_dec):,.0f}.  "
            f"Stop {float(result.stop_price):,.0f}.  "
            f"Target {float(result.target_price):,.0f}.",
            bold=True,
        ))
    _sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")
