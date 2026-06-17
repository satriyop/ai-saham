"""
CLI commands for foreign accumulation screening and universe management.

Commands:
  saham swing screen  — scan stocks for foreign accumulation patterns
  saham swing log     — log a candidate to the trade journal
  saham swing review  — review journal forward returns
  saham universe list              — show configured ticker universes
  saham universe update            — refresh universe lists from IDX (future)

Layer: Adapter
"""

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    load_universe_meta,
    resolve_tickers,
)
from src.application.use_case.assess_risk import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.accumulation_audit import (
    AccumulationAuditRequest,
    AccumulationAuditResponse,
    AccumulationAuditUseCase,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenResponse,
    AccumulationScreenUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeUseCase,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_screener_config_typed

_SC = _load_swing_screener_config_typed()
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

def _make_stockbit_providers(db_path: Path) -> "tuple[StockbitCorporateActionRepository | None, StockbitSeasonalityProvider | None]":
    """Return (corp_action_repo, seasonality_provider) sharing one Stockbit session.

    Both return None when no authenticated session exists — screener degrades gracefully.
    Single provider instance ensures the token is fetched once and cached for 30 minutes.
    """
    try:
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        provider = StockbitPlaywrightBrokerProvider()
        if not provider.is_authenticated():
            return None, None
        corp_repo = StockbitCorporateActionRepository(broker_provider=provider, db_path=db_path)
        season_prov = StockbitSeasonalityProvider(broker_provider=provider)
        return corp_repo, season_prov
    except Exception:
        return None, None


accumulation_app = typer.Typer(
    name="accumulation",
    help="Foreign accumulation screener",
    no_args_is_help=True,
)

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (LQ45, IDX80, IDXComp100)",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")
FOREIGN_BOUNCE_PRESET = "foreign-bounce"
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")
FOREIGN_BOUNCE_MAX_HOLD_DAYS = 10
# Broker tier sets are loaded from config/swing_screener.yaml via _SC.
# (Previously hardcoded here with stale CS entry — now driven by config.)

# Table widths
_TABLE_WIDTH = 93
_SEP_WIDTH = 91


@dataclass(frozen=True)
class ScreenBrokerQuality:
    """Compact named-broker context for screener output."""

    label: str
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    sessions: int
    through_date: date
    source: str

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "sessions": self.sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
        }


def _format_value(value: Decimal) -> str:
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


def _broker_tier(code: str) -> str:
    code_upper = code.upper()
    if code_upper in _SC.smart_money_brokers:
        return "smart"
    if code_upper in _SC.noise_brokers:
        return "noise"
    return "neutral"


def _screen_broker_quality_label(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> str:
    """Return a compact label for named-broker flow composition."""
    positive_total = sum(
        value
        for value in (smart_flow, noise_flow, neutral_flow)
        if value > Decimal("0")
    )
    negative_total = sum(
        abs(value)
        for value in (smart_flow, noise_flow, neutral_flow)
        if value < Decimal("0")
    )

    if negative_total > positive_total:
        if smart_flow < Decimal("0") and abs(smart_flow) >= abs(noise_flow):
            return "smart-"
        if noise_flow < Decimal("0"):
            return "noise-"
        return "dist"

    if smart_flow > Decimal("0") and smart_flow >= noise_flow and smart_flow >= neutral_flow:
        return "smart+"
    if noise_flow > Decimal("0") and noise_flow >= smart_flow and noise_flow >= neutral_flow:
        return "noise+"
    if neutral_flow != Decimal("0"):
        return "mixed"
    return "n/a"


def _build_screen_broker_quality(
    ticker: str,
    broker_repo: SQLiteBrokerRepository,
    as_of_date: date | None = None,
    window_sessions: int = 5,
) -> ScreenBrokerQuality | None:
    """
    Summarize named top-broker rows for screener context.

    This uses all named top buyers/sellers returned by Stockbit summaries.
    It is separate from aggregate foreign-flow scoring.
    """
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    detail_summaries = [
        summary for summary in summaries if summary.top_buyers or summary.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")

    def add_flow(code: str, signed_value: Decimal) -> None:
        nonlocal smart_flow, noise_flow, neutral_flow
        tier = _broker_tier(code)
        if tier == "smart":
            smart_flow += signed_value
        elif tier == "noise":
            noise_flow += signed_value
        else:
            neutral_flow += signed_value

    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                add_flow(tx.broker_code, tx.net_value)
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                add_flow(tx.broker_code, tx.net_value)

    latest = detail_summaries[-1]
    return ScreenBrokerQuality(
        label=_screen_broker_quality_label(smart_flow, noise_flow, neutral_flow),
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
    )


def _broker_quality_by_ticker(
    tickers: list[str],
    broker_repo: SQLiteBrokerRepository,
    as_of_date: date | None,
) -> dict[str, ScreenBrokerQuality]:
    quality: dict[str, ScreenBrokerQuality] = {}
    for ticker in tickers:
        item = _build_screen_broker_quality(
            ticker=ticker,
            broker_repo=broker_repo,
            as_of_date=as_of_date,
        )
        if item:
            quality[ticker.upper()] = item
    return quality


def _fmt_score(s: float | None) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= _SC.enter_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= _SC.watch_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def _classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = _SC.coiled_spring_min_score
    hot = [w for w in windows if candidates_by_window.get(w) and candidates_by_window[w].score >= threshold]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if c and c.score >= threshold and c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile:
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


def _fmt_optional_float(value: float | None, suffix: str = "") -> str:
    return "missing" if value is None else f"{value:.1f}{suffix}"


def _foreign_bounce_decision(
    candidate: AccumulationCandidate | None,
) -> tuple[str, tuple[str, ...]]:
    if candidate is None:
        return "AVOID", ("No accumulation/broker-flow candidate available",)

    gates = (
        (
            "score",
            candidate.score >= _SC.gate_min_score,
            f"{candidate.score:.1f}",
            f">= {_SC.gate_min_score:.0f}",
        ),
        (
            "vwap_disc_pct",
            candidate.vwap_discount_pct is not None
            and candidate.vwap_discount_pct >= _SC.gate_min_vwap_discount_pct,
            _fmt_optional_float(candidate.vwap_discount_pct, "%"),
            f">= +{_SC.gate_min_vwap_discount_pct:.0f}%",
        ),
        (
            "trend",
            candidate.trend == _SC.gate_required_trend,
            candidate.trend,
            _SC.gate_required_trend,
        ),
        (
            "flow_pct",
            candidate.avg_flow_ratio is not None and candidate.avg_flow_ratio >= _SC.gate_min_flow_ratio_pct,
            _fmt_optional_float(candidate.avg_flow_ratio, "%"),
            f">= +{_SC.gate_min_flow_ratio_pct:.0f}%",
        ),
        (
            "RSI present",
            candidate.rsi is not None,
            _fmt_optional_float(candidate.rsi),
            "present",
        ),
        (
            "RSI",
            candidate.rsi is not None and candidate.rsi <= _SC.gate_max_rsi,
            _fmt_optional_float(candidate.rsi),
            f"<= {_SC.gate_max_rsi:.0f}",
        ),
    )
    failed = tuple(
        f"{label}: {actual} (required {required})"
        for label, passed, actual, required in gates
        if not passed
    )
    if not failed:
        return "ENTER", failed
    if candidate.score >= _SC.gate_min_score or len(failed) <= _SC.watch_max_failed_gates:
        return "WATCH", failed
    return "AVOID", failed


def _percent_plan(entry: Decimal) -> tuple[Decimal, Decimal]:
    stop = entry * (Decimal("1") - FOREIGN_BOUNCE_STOP_LOSS / Decimal("100"))
    target = entry * (Decimal("1") + FOREIGN_BOUNCE_TAKE_PROFIT / Decimal("100"))
    return stop, target


_STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}
_STRAT_COLOR  = {
    "LOW_RISK":  typer.colors.GREEN,
    "HIGH_RISK": typer.colors.RED,
    "MODERATE":  typer.colors.BRIGHT_BLACK,
}


def _display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    granular: bool,
    vwap_only: bool,
    squeeze_only: bool,
    show_breakdown: bool,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    """Render accumulation screener results as terminal table."""
    candidates = response.candidates
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]
    if squeeze_only:
        candidates = [c for c in candidates if c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile]

    candidates = candidates[:top_n]

    typer.echo("")
    typer.echo("=" * _TABLE_WIDTH)
    typer.echo(
        f"FOREIGN ACCUMULATION — {universe_label.upper()} "
        f"| {response.window_days} sessions | {response.screened_at}"
    )
    typer.echo("=" * _TABLE_WIDTH)

    if not candidates:
        typer.echo("No candidates found matching the criteria.")
        typer.echo(
            f"Checked {response.total_tickers_checked} tickers, "
            f"skipped {response.tickers_skipped} (insufficient data)."
        )
        typer.echo("=" * _TABLE_WIDTH)
        return

    strat_hdr = f" {'STRAT':>6}" if strategy_signals is not None else ""
    sep_w = _SEP_WIDTH + (8 if strategy_signals is not None else 0)
    header = (
        f"{'#':>3} {'TICKER':<7} {'SCORE':>6} {'STREAK':>7} {'NET_DAYS':>9}"
        f" {'NET_VALUE':>12} {'FLOW%':>6} {'F_VWAP%':>8} {'RSI':>6} {'BB%ILE':>7} {'TREND':>5}"
        f"{strat_hdr}"
    )
    typer.echo(header)
    typer.echo("-" * sep_w)

    for i, c in enumerate(candidates, 1):
        net_days_str = f"{c.net_buy_days}/{c.total_days}"
        vwap_str = f"{c.vwap_discount_pct:+.1f}%" if c.vwap_discount_pct is not None else "   —  "
        rsi_str = f"{c.rsi:.1f}" if c.rsi is not None else "  —"
        streak_str = f"{c.consecutive_streak}s"
        flow_str = f"{c.avg_flow_ratio:+.1f}" if c.avg_flow_ratio is not None else "   —"
        if c.bb_width_pctile is not None:
            pct_int = int(c.bb_width_pctile * 100)
            bb_color = typer.colors.GREEN if c.bb_width_pctile <= _SC.coiled_spring_bb_pctile else (
                typer.colors.YELLOW if c.bb_width_pctile <= 0.40 else typer.colors.WHITE
            )
            bb_str = typer.style(f"{pct_int:>4}%", fg=bb_color)
        else:
            bb_str = typer.style("  — ", fg=typer.colors.BRIGHT_BLACK)

        # Color score
        if c.score >= _SC.enter_min_score:
            score_color = typer.colors.GREEN
        elif c.score >= _SC.watch_min_score:
            score_color = typer.colors.YELLOW
        else:
            score_color = typer.colors.WHITE

        strat_col = ""
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            col = _STRAT_COLOR.get(raw, typer.colors.WHITE)
            strat_col = " " + typer.style(f"{sym:>6}", fg=col, bold=(raw == "LOW_RISK"))

        line = (
            f"{i:>3} {c.ticker:<7} "
            + typer.style(f"{c.score:>6.1f}", fg=score_color)
            + f" {streak_str:>7} {net_days_str:>9} {_format_value(c.total_net_value):>12}"
            + f" {flow_str:>6} {vwap_str:>8} {rsi_str:>6} {bb_str}  {c.trend:>5}"
            + strat_col
        )
        typer.echo(line)

        if show_breakdown and c.score_breakdown:
            bd = c.score_breakdown
            typer.echo(
                f"    [cons={bd.get('cons', 0):.1f} streak={bd.get('streak', 0):.1f}"
                f" vwap={bd.get('vwap', 0):.1f} rsi={bd.get('rsi', 0):.1f}"
                f" flow={bd.get('flow', 0):.1f} bb={bd.get('bb', 0):.1f}"
                f" inst={bd.get('inst', 0):.1f}]"
            )

        if c.seasonal_edge is not None:
            se = c.seasonal_edge
            se_color = typer.colors.GREEN if se.is_tailwind else (typer.colors.RED if se.is_headwind else typer.colors.WHITE)
            typer.echo(typer.style(f"    SEASONAL {se.label} (score {se.score:+.2f})", fg=se_color))

        if c.dividend_risk:
            typer.echo(typer.style("    ⚠ DIVIDEND RISK", fg=typer.colors.YELLOW))
        if c.rights_issue_risk:
            typer.echo(typer.style("    ⚠ RIGHTS ISSUE", fg=typer.colors.YELLOW))

        if granular and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.bci_label == "CLUSTER":
                broker_line += "  " + typer.style(f"[★ BCI:{c.bci_label}({c.bci_tier1_count}T1)]", fg=typer.colors.CYAN)
            elif c.bci_label == "STABLE":
                broker_line += "  " + typer.style(f"[BCI:{c.bci_label}({c.bci_tier1_count}T1)]", fg=typer.colors.GREEN)
            elif c.bci_label == "RETAIL-LED":
                broker_line += "  " + typer.style("[BCI:RETAIL-LED]", fg=typer.colors.WHITE)
            typer.echo(broker_line)

    typer.echo("-" * _SEP_WIDTH)
    typer.echo(
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )
    typer.echo(f"Provider: {response.provider} (aggregate foreign flow)")
    if response.provider == "idx":
        typer.echo(
            "  For per-broker detail: run `saham stockbit login`, then fetch with `--provider stockbit-session`"
        )
    typer.echo("")
    typer.echo("FLOW%: avg net foreign % of total daily turnover (positive = accumulating)")
    typer.echo("F_VWAP%: positive = price < foreign avg buy cost basis (foreigners underwater)")
    typer.echo("BB%ILE: BB Width pctile vs last 60d — green(≤20%) = squeeze (coiled spring)")
    typer.echo("Score 0–120 | consistency 40 | streak 30 | VWAP 20 | RSI 10 | flow 10 | BB 10 | BCI 0/5/15")
    if strategy_signals is not None:
        typer.echo(
            f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )
    typer.echo("")
    typer.echo("Swing trade watchlist — cross-check with `saham intraday pre-open` for intraday entry timing.")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)


def _run_multi(
    use_case: AccumulationScreenUseCase,
    tickers: list[str],
    windows: list[int],
    base_request: AccumulationScreenRequest,
) -> dict[int, AccumulationScreenResponse]:
    """Run screener for each window. Always min_score=0 to get full picture."""
    return {
        w: use_case.execute(AccumulationScreenRequest(
            tickers=tickers,
            window_days=w,
            min_net_buy_days=base_request.min_net_buy_days,
            min_score=0.0,
            rsi_period=base_request.rsi_period,
            sma_period=base_request.sma_period,
            tier1_broker_codes=base_request.tier1_broker_codes,
        ))
        for w in windows
    }


def _display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: "date",
    broker_quality: dict[str, ScreenBrokerQuality] | None = None,
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
        scores = [c.score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        try:
            w = int(sort_by.rstrip("ds"))
            c = pw.get(w)
            return c.score if c else 0.0
        except (ValueError, AttributeError):
            return sum(scores) / len(scores)

    rows = sorted(by_ticker.items(), key=sort_key, reverse=True)[:top_n]

    typer.echo("")
    typer.echo("=" * _TABLE_WIDTH)
    typer.echo(
        f"FOREIGN ACCUMULATION — {universe_label.upper()} "
        f"| MULTI-WINDOW | {screened_at}"
    )
    typer.echo("=" * _TABLE_WIDTH)

    if not rows:
        typer.echo("No candidates found matching the criteria.")
        typer.echo("=" * _TABLE_WIDTH)
        return

    win_headers = "  ".join(f"{w:>4}s" for w in windows)
    typer.echo(f"{'#':>3} {'TICKER':<7} {win_headers}  {'PATTERN':<18} {'TREND':>5} {'BRK':>7}")
    typer.echo("-" * _SEP_WIDTH)

    for i, (tk, pw) in enumerate(rows, 1):
        cells = "  ".join(_fmt_score(pw.get(w).score if pw.get(w) else None) for w in windows)
        pattern = _classify_pattern(windows, pw)
        trend = next((c.trend for w in sorted(windows) for c in [pw.get(w)] if c), "—")
        quality = (broker_quality or {}).get(tk)
        brk = quality.label if quality else "n/a"
        typer.echo(f"{i:>3} {tk:<7} {cells}  {pattern:<18} {trend:>5} {brk:>7}")

    sample_resp = next(iter(results.values()))
    typer.echo("-" * _SEP_WIDTH)
    typer.echo(
        f"Checked: {sample_resp.total_tickers_checked} | "
        f"Shown: {len(rows)} | "
        f"Provider: {sample_resp.provider}"
    )
    typer.echo("Score ≥70 green | ≥40 yellow | <40 white")
    typer.echo("Patterns: sustained | building | fresh rotation | long-term only | coiled spring | weak")
    typer.echo("BRK: named top-broker quality; smart+/noise+ = buyer-led, smart-/noise- = seller-led, n/a = no detail")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * _TABLE_WIDTH)


def _print_column_guide() -> None:
    """Print a terminal-friendly reference guide for every column and signal."""

    def _h(text: str) -> None:
        typer.echo("")
        typer.echo(typer.style(f"  {text}", fg=typer.colors.CYAN, bold=True))
        typer.echo(typer.style("  " + "─" * (len(text) + 2), fg=typer.colors.BRIGHT_BLACK))

    def _row(label: str, value: str) -> None:
        typer.echo(f"    {typer.style(label, fg=typer.colors.YELLOW):<30} {value}")

    typer.echo("")
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo(typer.style("  FOREIGN ACCUMULATION SCREENER — COLUMN GUIDE", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")
    typer.echo("  Detects stocks being quietly bought by foreign institutions over")
    typer.echo("  multiple days. When foreigners accumulate consistently AND are")
    typer.echo("  'underwater' (bought higher than today's price), IHSG stocks")
    typer.echo("  resolve upward 65–70% of the time within 10–20 trading days.")
    typer.echo("  This is a swing trade watchlist (5–20 day horizon).")

    # ── SCORE ──
    _h("SCORE  (0–120)")
    typer.echo("  Composite signal strength. Combines all signals below into one number.")
    typer.echo("  Higher = more confident that accumulation is real and setup is clean.")
    _row("≥ 70 (green)", "Strong signal — worth researching")
    _row("40–69 (yellow)", "Moderate — watch, wait for confirmation")
    _row("< 40 (white)", "Weak — likely noise, skip")
    typer.echo("")
    typer.echo("  Use --breakdown to see exactly how each component contributed.")

    # ── STREAK ──
    _h("STREAK  — Consecutive Buy Days")
    typer.echo("  How many trading days IN A ROW foreigners ended up as net buyers,")
    typer.echo("  counting backwards from today. A streak means systematic intent.")
    _row("1–2d", "Inconclusive")
    _row("3–4d", "Noteworthy — watch this ticker")
    _row("5–7d", "Strong — likely intentional accumulation")
    _row("8d+", "Very strong — institution is committed")
    typer.echo("")
    typer.echo("  Scoring: exponential curve (τ=7d). 7d streak ≈ 63% of max,")
    typer.echo("  14d ≈ 86%. Longer streaks always score higher — no hard cap.")

    # ── NET_DAYS ──
    _h("NET_DAYS  — Consistency Ratio  (e.g. 5/7)")
    typer.echo("  Net buy days / total broker sessions in the window. 5/7 =")
    typer.echo("  foreigners bought on 5 of the last 7 broker sessions. This is")
    typer.echo("  the highest-weight signal (40 pts).")
    _row("100% (4/4, 7/7)", "Every day was a buy — strong conviction")
    _row("70–99%", "Most days positive — healthy trend")
    _row("50–69%", "Mixed — watch for deterioration")
    _row("< 50%", "More sell days than buy — not accumulation")
    typer.echo("")
    typer.echo("  A stock with 4/4 is stronger than 10/30 even if the streak looks similar.")

    # ── NET_VALUE ──
    _h("NET_VALUE  — Total Net Foreign Flow (IDR)")
    typer.echo("  Total (foreign buys − foreign sells) over the broker-session window in IDR.")
    typer.echo("  Confirms real money is behind the consistency signal.")
    _row("+19.4B", "Net bought Rp 19.4 billion — meaningful size")
    _row("+10M", "Net bought Rp 10 million — may be too small")
    typer.echo("")
    typer.echo("  T = trillion  |  B = billion  |  M = million  (IDR)")

    # ── FLOW% ──
    _h("FLOW%  — Foreign Dominance of Daily Volume")
    typer.echo("  Average % of total daily turnover that was net foreign buying.")
    typer.echo("  Unlike NET_VALUE (absolute IDR), this is relative — a mid-cap")
    typer.echo("  at 35% FLOW% is a stronger signal than a large-cap at 3%.")
    _row("0–5%", "Minor participation")
    _row("5–15%", "Meaningful foreign interest")
    _row("15–30%", "Foreigners are a major force in this stock")
    _row("30%+", "Foreigners dominating — very strong signal")
    typer.echo("")
    typer.echo("  Scoring: contributes up to 10 pts, saturates at 20% flow ratio.")

    # ── F_VWAP% ──
    _h("F_VWAP%  — Foreigners' Profit / Loss on Position")
    typer.echo("  Compares foreigners' average buy price (VWAP) to today's price.")
    typer.echo("")
    typer.echo("  POSITIVE (+8.4%) = foreigners bought HIGHER than today's price.")
    typer.echo("  They are underwater (in a paper loss) and motivated to defend.")
    typer.echo("  When they keep buying despite a loss, they expect a recovery.")
    typer.echo("  This creates a price floor — they absorb selling to protect position.")
    typer.echo("")
    typer.echo("  NEGATIVE (−1.9%) = foreigners are in profit. Less urgency to defend.")
    _row("  > +5%", "Meaningfully underwater — strong defense motive")
    _row("  +1% to +5%", "Slightly underwater — moderate signal")
    _row("  < 0%", "In profit — less motivated to defend")
    _row("  — (dash)", "Insufficient buy data to compute VWAP")
    typer.echo("")
    typer.echo("  Scoring: linear ramp. 10% underwater = full 20 pts. 5% = 10 pts.")

    # ── RSI ──
    _h("RSI  — Room Left to Run  (14-day)")
    typer.echo("  Relative Strength Index — measures price momentum (0–100).")
    typer.echo("  For accumulation, you want to enter BEFORE a move, not after.")
    _row("  > 70", "Overbought — most of the move already happened")
    _row("  55–70", "Building momentum — getting stretched")
    _row("  40–55", "Healthy — moving but not overextended")
    _row("  25–40", "Weak/recovering — ideal entry zone")
    _row("  < 25", "Severe panic — high risk, possible capitulation")
    typer.echo("")
    typer.echo("  Scoring: tent peak at RSI=40 (10 pts). Zero at RSI≤25 or ≥75.")
    typer.echo("  RSI 40 with a 5-day streak = smart money re-entering during weakness.")

    # ── BB%ILE ──
    _h("BB%ILE  — Bollinger Band Squeeze  (green ≤ 20%)")
    typer.echo("  Percentile rank of today's Bollinger Band width vs last 60 days.")
    typer.echo("  BB Width measures price channel size — narrow = compressed volatility.")
    typer.echo("")
    typer.echo("  LOW BB%ILE = the band is TIGHTER than usual = SQUEEZE.")
    typer.echo("  When a stock trades flat (low vol) while foreigners accumulate,")
    typer.echo("  it is a 'coiled spring'. Compression releases suddenly on a catalyst.")
    _row("  ≤ 20% (green)", "Squeeze — coiled spring, watch closely")
    _row("  21–40% (yellow)", "Moderately tight — building")
    _row("  > 40%", "Normal or expanding volatility")
    _row("  — (dash)", "< 60 days of price data in local DB")
    typer.echo("")
    typer.echo("  Scoring: bottom 20th pctile earns 5–10 pts; 40th pctile earns 0–5 pts.")
    typer.echo("  Use --squeeze-only to filter exclusively for these setups.")

    # ── TREND ──
    _h("TREND  — Price vs SMA20")
    typer.echo("  Whether the stock is above or below its 20-day moving average.")
    _row("  UP", "> 2% above SMA20 — uptrend")
    _row("  DOWN", "> 2% below SMA20 — downtrend")
    _row("  SIDE", "Within ±2% of SMA20 — ranging")
    typer.echo("")
    typer.echo("  For accumulation setups, DOWN or SIDE is often ideal — you want to")
    typer.echo("  enter BEFORE the trend turns UP, not after the move has started.")

    # ── PATTERN (multi-window) ──
    _h("PATTERN  — Multi-Window Summary  (--multi only)")
    typer.echo("  Labels what the 7d/30d/90d score comparison reveals.")
    _row("  sustained", "Score ≥60 on all 3 windows — months of buildup, highest conviction")
    _row("  building", "Strong 7d+30d, weaker 90d — accumulation intensifying recently")
    _row("  fresh rotation", "Strong 7d only — very recent, needs time to confirm")
    _row("  long-term only", "Strong 90d, weak recent — may be complete, watch for exit")
    _row("  coiled spring", "Squeeze + score ≥60 on any window — compressed, ready to break")
    _row("  weak", "No window scores ≥60 — not a meaningful setup")

    # ── BREAKDOWN ──
    _h("SCORE BREAKDOWN  (--breakdown flag)")
    typer.echo("  Shows exactly how each component contributed to the total score.")
    typer.echo("  Format: [cons=X streak=X vwap=X rsi=X flow=X bb=X inst=X]")
    _row("  cons", "Up to 40 pts — net buy day consistency")
    _row("  streak", "Up to 30 pts — consecutive buy days (exponential)")
    _row("  vwap", "Up to 20 pts — how underwater foreigners are")
    _row("  rsi", "Up to 10 pts — RSI headroom (tent at 40)")
    _row("  flow", "Up to 10 pts — avg % of daily turnover that's foreign")
    _row("  bb", "Up to 10 pts — BB Width squeeze intensity")
    _row("  inst", "0/5/15 pts — BCI: RETAIL-LED/STABLE/CLUSTER (Stockbit only)")
    typer.echo("")
    typer.echo("  If a stock scores lower than expected, breakdown shows which signal")
    typer.echo("  is missing. E.g. vwap=0 means foreigners are in profit — no defense motive.")

    # ── IDEAL SETUP ──
    _h("IDEAL CANDIDATE CHECKLIST")
    typer.echo("  In priority order:")
    typer.echo("    1. PATTERN = sustained or coiled spring  (multi-window confirms)")
    typer.echo("    2. STREAK ≥ 5d                          (systematic, not opportunistic)")
    typer.echo("    3. F_VWAP% > 0%                         (foreigners defending position)")
    typer.echo("    4. BB%ILE ≤ 20% (green)                 (compressed, spring loaded)")
    typer.echo("    5. RSI between 30–50                    (room to run)")
    typer.echo("    6. FLOW% > 15%                          (foreigners dominating volume)")
    typer.echo("    7. NET_DAYS ≥ 70%                       (consistent, not just a streak)")
    typer.echo("")
    typer.echo("  No single signal is definitive. A stock meeting 5 of 7 criteria is")
    typer.echo("  a much stronger candidate than one barely crossing a score threshold.")

    # ── TIPS ──
    _h("QUICK TIPS")
    typer.echo("  Run --multi first for the daily overview — one command, three windows.")
    typer.echo("  Use --squeeze-only to surface 'coiled spring' setups.")
    typer.echo("  Deep-dive: saham broker flow <TICKER> --days 30")
    typer.echo("             saham risk <TICKER> --profile balanced --with-sentiment")
    typer.echo("")
    typer.echo(typer.style("  DISCLAIMER: Analysis only. Not financial advice.", fg=typer.colors.BRIGHT_BLACK))
    typer.echo(typer.style("=" * 70, fg=typer.colors.CYAN))
    typer.echo("")


@accumulation_app.command("run")
def accumulation_run(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Universe: lq45, idx80, idxcomp100, cached",
        ),
    ] = None,
    window: Annotated[
        int,
        typer.Option(
            "--window", "-w",
            help="Analysis window in broker sessions (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_score: Annotated[
        Optional[float],
        typer.Option("--min-score", help="Minimum composite score (0–120, default: 70)", min=0),
    ] = None,
    vwap_only: Annotated[
        bool,
        typer.Option("--vwap-only", help="Only show stocks where foreigners are underwater"),
    ] = False,
    squeeze_only: Annotated[
        bool,
        typer.Option("--squeeze-only", help="Only show stocks in BB squeeze (BB width pctile ≤ 20%)"),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show top N results", min=1),
    ] = 20,
    granular: Annotated[
        bool,
        typer.Option("--granular", help="Show per-broker detail (Stockbit data required)"),
    ] = False,
    show_breakdown: Annotated[
        bool,
        typer.Option("--breakdown", help="Show per-component score breakdown under each row"),
    ] = False,
    multi: Annotated[
        bool,
        typer.Option("--multi", help="Show scores across multiple windows side-by-side"),
    ] = False,
    windows: Annotated[
        Optional[str],
        typer.Option("--windows", help="Comma-separated broker-session windows for --multi (default: 7,30,90)"),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort-by",
            help=(
                "In --multi mode, sort by: avg|max|7s|30s|90s "
                "(legacy 7d/30d/90d also accepted; default: avg)"
            ),
        ),
    ] = "avg",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    guide: Annotated[
        bool,
        typer.Option("--guide", help="Print column reference guide and exit (no screen needed)"),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Print column guide appended after results"),
    ] = False,
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy", "-S",
            help="Show strategy signal column alongside accum score (e.g. williams-r-bounce)",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Screen stocks for foreign accumulation patterns.

    Scores each ticker 0–120 based on: consistency of daily foreign buying,
    consecutive buy streak, whether foreigners are underwater (VWAP vs price),
    RSI headroom, foreign flow as % of total turnover, and BB Width squeeze.

    Run `saham update --universe lq45` first to ensure fresh data.

    Examples:
        saham swing screen --universe lq45
        saham swing screen --universe lq45 --window 30
        saham swing screen --universe lq45 --multi
        saham swing screen --universe lq45 --multi --sort-by 30s
        saham swing screen --universe lq45 --min-score 50 --top 10
        saham swing screen BBCA BBRI BMRI --window 7
        saham swing screen --universe lq45 --vwap-only
        saham swing screen --universe lq45 --squeeze-only
        saham swing screen --universe lq45 --granular
        saham swing screen --universe lq45 --breakdown
        saham swing screen --universe lq45 --explain
        saham swing screen --guide
        saham swing screen --universe lq45 --format json
    """
    if guide:
        _print_column_guide()
        return

    resolved_db = db_path or DEFAULT_DB_PATH

    if min_score is None:
        min_score = float(get_swing_default("min_score", 70.0))

    # Resolve tickers
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to screen. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    universe_label = universe or f"{len(ticker_list)} tickers"

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    _corp_repo, _season_prov = _make_stockbit_providers(resolved_db)
    use_case = AccumulationScreenUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
        corporate_action_repo=_corp_repo,
        seasonality_provider=_season_prov,
    )

    base_request = AccumulationScreenRequest(
        tickers=ticker_list,
        window_days=window,
        min_net_buy_days=max(1, min_streak),
        min_score=min_score,
        tier1_broker_codes=_SC.tier1_broker_codes,
    )

    # --- Multi-window mode ---
    if multi:
        window_list = [int(w.strip()) for w in (windows or "7,30,90").split(",")]
        if output_format != "json":
            typer.echo(
                f"Screening {len(ticker_list)} tickers | windows: "
                f"{', '.join(str(w) + ' sessions' for w in window_list)}..."
            )
        multi_results = _run_multi(use_case, ticker_list, window_list, base_request)
        screened_at = next(iter(multi_results.values())).screened_at
        broker_quality = _broker_quality_by_ticker(
            tickers=ticker_list,
            broker_repo=broker_repo,
            as_of_date=screened_at,
        )

        if output_format == "json":
            by_ticker: dict = {}
            for w, resp in multi_results.items():
                for c in resp.candidates:
                    by_ticker.setdefault(c.ticker, {})[f"{w}_sessions"] = c.to_dict()
            for ticker_key, quality in broker_quality.items():
                by_ticker.setdefault(ticker_key, {})["broker_quality"] = quality.to_dict()
            typer.echo(json.dumps({
                "mode": "multi",
                "windows": [f"{w}_sessions" for w in sorted(multi_results.keys())],
                "screened_at": str(screened_at),
                "tickers": by_ticker,
            }, indent=2, default=str))
            return

        _display_multi(
            results=multi_results,
            universe_label=universe_label,
            top_n=top,
            sort_by=sort_by,
            squeeze_only=squeeze_only,
            screened_at=screened_at,
            broker_quality=broker_quality,
        )
        if explain:
            _print_column_guide()
        return

    # --- Single-window mode ---
    if output_format != "json":
        typer.echo(
            f"Screening {len(ticker_list)} tickers | {window} sessions..."
        )
    response = use_case.execute(base_request)

    # Apply streak filter post-scoring
    if min_streak > 0:
        response.candidates = [
            c for c in response.candidates if c.consecutive_streak >= min_streak
        ]

    if output_format == "json":
        data = {
            "screened_at": str(response.screened_at),
            "window_days": response.window_days,
            "total_checked": response.total_tickers_checked,
            "skipped": response.tickers_skipped,
            "provider": response.provider,
            "candidates": [c.to_dict() for c in response.candidates[:top]],
        }
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    # Optional strategy signal column
    strategy_signals: dict[str, str] = {}
    if strategy:
        registry = create_indicator_registry(
            broker_repository=broker_repo,
            market_repository=market_repo,
        )
        try:
            strat_loader = StrategyLoader(registry=registry)
            rules_path = strat_loader.resolve(strategy)
            risk_uc = AssessRiskUseCase(repository=market_repo, registry=registry)
            visible = response.candidates[:top]
            for c in visible:
                try:
                    req = AssessRiskRequest(ticker=c.ticker, rules_file=rules_path)
                    res = risk_uc.execute(req)
                    strategy_signals[c.ticker] = res.assessment.risk_level_name
                except Exception:
                    strategy_signals[c.ticker] = "?"
        except StrategyNotFoundError as e:
            typer.echo(f"⚠ Strategy not found: {e}", err=True)

    _display_results(
        response=response,
        universe_label=universe_label,
        top_n=top,
        granular=granular,
        vwap_only=vwap_only,
        squeeze_only=squeeze_only,
        show_breakdown=show_breakdown,
        strategy_signals=strategy_signals or None,
        strategy_name=strategy,
    )
    if explain:
        _print_column_guide()


def _display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))
    typer.echo(
        typer.style(
            "FOREIGN ACCUMULATION HISTORICAL AUDIT",
            fg=typer.colors.CYAN,
            bold=True,
        )
    )
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))
    typer.echo(
        f"Period: {response.start_date} to {response.end_date} | "
        f"window: {response.window_days} sessions | replay dates: {response.total_replay_dates} | "
        f"tickers: {response.total_tickers}"
    )
    typer.echo(
        f"Signals: {response.total_records} | "
        f"Skipped no forward data: {response.skipped_no_forward_data}"
    )
    typer.echo(
        "Read fixed-hold rows as: if you bought every matching signal at the signal-date "
        "close, what happened after 5/10/20 trading days."
    )
    typer.echo("")

    if not response.records:
        typer.echo("No replayed signals matched the audit filters.")
        return

    typer.echo(
        f"{'DIMENSION':<14} {'BUCKET':<12} {'N':>6} "
        f"{'AVG5D':>9} {'AVG10D':>9} {'WIN10D':>9} "
        f"{'AVG20D':>9} {'MAXUP':>9} {'MAXDD':>9}"
    )
    typer.echo("-" * 96)
    for stat in response.group_stats[:top_groups]:
        def fmt(v: float | None) -> str:
            return "—" if v is None else f"{v:+.2f}%"

        win = "—" if stat.win_rate_10d_pct is None else f"{stat.win_rate_10d_pct:.1f}%"
        typer.echo(
            f"{stat.dimension:<14} {stat.bucket:<12} {stat.count:>6} "
            f"{fmt(stat.avg_return_5d_pct):>9} {fmt(stat.avg_return_10d_pct):>9} "
            f"{win:>9} {fmt(stat.avg_return_20d_pct):>9} "
            f"{fmt(stat.avg_max_upside_pct):>9} {fmt(stat.avg_max_drawdown_pct):>9}"
        )

    if response.exit_simulations:
        typer.echo("")
        typer.echo("EXIT SIMULATION")
        typer.echo("-" * 96)
        best = response.exit_simulations[0]
        avg_ret = (
            "N/A" if best.avg_return_pct is None
            else f"{best.avg_return_pct:+.2f}%"
        )
        win = "N/A" if best.win_rate_pct is None else f"{best.win_rate_pct:.1f}%"
        avg_days = (
            "N/A" if best.avg_holding_days is None
            else f"{best.avg_holding_days:.1f}d"
        )
        typer.echo(
            "Rows below simulate managed exits using daily high/low: stop is checked "
            "first, then target, otherwise exit at max-hold close."
        )
        typer.echo(
            f"Best by AVG_RET: TP {best.take_profit_pct:g}%, "
            f"SL {best.stop_loss_pct:g}%, max hold {best.max_hold_days}d -> "
            f"avg {avg_ret}, win {win}, avg hold {avg_days}."
        )
        if response.total_records < 30:
            typer.echo(
                "Caution: sample is small (<30 signals). Treat this as a hypothesis "
                "to retest on more dates/universes, not a final rule."
            )
        typer.echo("")
        typer.echo(
            f"{'TP%':>6} {'SL%':>6} {'HOLD':>6} {'N':>6} "
            f"{'AVG_RET':>9} {'WIN':>8} {'AVG_DAYS':>9} "
            f"{'STOP':>8} {'TARGET':>8} {'MAXHOLD':>8} {'AVG_DD':>9}"
        )
        for stat in response.exit_simulations[:top_groups]:
            def fmt_pct(v: float | None, signed: bool = False) -> str:
                if v is None:
                    return "—"
                return f"{v:+.2f}%" if signed else f"{v:.1f}%"

            avg_days = "—" if stat.avg_holding_days is None else f"{stat.avg_holding_days:.1f}"
            typer.echo(
                f"{stat.take_profit_pct:>6.1f} {stat.stop_loss_pct:>6.1f} "
                f"{stat.max_hold_days:>6} {stat.count:>6} "
                f"{fmt_pct(stat.avg_return_pct, signed=True):>9} "
                f"{fmt_pct(stat.win_rate_pct):>8} {avg_days:>9} "
                f"{fmt_pct(stat.stop_rate_pct):>8} "
                f"{fmt_pct(stat.target_rate_pct):>8} "
                f"{fmt_pct(stat.max_hold_rate_pct):>8} "
                f"{fmt_pct(stat.avg_max_drawdown_pct, signed=True):>9}"
            )

    typer.echo("")
    typer.echo("COLUMN GUIDE")
    typer.echo("-" * 40)
    typer.echo("AVG5D/10D/20D: passive close-to-close return after that many trading days.")
    typer.echo("MAXUP/MAXDD: average best/worst close-to-close move inside the horizon.")
    typer.echo("AVG_RET: simulated exit return after TP/SL/max-hold rules.")
    typer.echo("WIN: percent of simulated exits with positive return.")
    typer.echo("STOP/TARGET/MAXHOLD: how often each exit reason happened.")
    typer.echo("AVG_DD: average intratrade drawdown using daily low before exit.")

    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")

    typer.echo("")
    typer.echo("DISCLAIMER: Historical audit only. Not trading advice.")
    typer.echo(typer.style("=" * 96, fg=typer.colors.CYAN))


def _write_audit_csv(response: AccumulationAuditResponse, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in response.records]
    fieldnames = list(rows[0].keys()) if rows else [
        "signal_date", "ticker", "score", "streak", "net_buy_ratio",
        "total_net_value", "flow_pct", "vwap_disc_pct", "rsi", "bb_pctile",
        "trend", "broker_quality", "current_price", "return_5d_pct", "return_10d_pct",
        "return_20d_pct", "max_upside_pct", "max_drawdown_pct",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_float_grid(value: str, option_name: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated numbers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive numbers")
    return parsed


def _parse_int_grid(value: str, option_name: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated integers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive integers")
    return parsed


AUDIT_PRESETS = {
    "foreign-bounce": {
        "universe": "idx80",
        "window": 7,
        "min_score": 70.0,
        "min_net_buy_days": 2,
        "min_vwap_disc": 3.0,
        "trend": "SIDE",
        "min_flow_pct": 5.0,
        "require_rsi": True,
        "max_rsi": 60.0,
        "simulate_exits": True,
        "take_profits": "4,5,6",
        "stop_losses": "3,5,7",
        "max_holds": "3,5,7,10",
    },
}


@accumulation_app.command("audit")
def accumulation_audit(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = None,
    preset: Annotated[
        Optional[str],
        typer.Option("--preset", help="Audit preset: foreign-bounce"),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="Audit start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Audit end date, YYYY-MM-DD (default: today)"),
    ] = None,
    window: Annotated[
        Optional[int],
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = None,
    min_score: Annotated[
        Optional[float],
        typer.Option("--min-score", help="Minimum composite score to audit", min=0),
    ] = None,
    min_net_buy_days: Annotated[
        Optional[int],
        typer.Option("--min-net-buy-days", help="Minimum foreign net-buy days", min=1),
    ] = None,
    min_vwap_disc: Annotated[
        Optional[float],
        typer.Option(
            "--min-vwap-disc",
            help="Require VWAP discount at least this percent",
        ),
    ] = None,
    trend: Annotated[
        Optional[str],
        typer.Option("--trend", help="Require trend bucket: UP, SIDE, or DOWN"),
    ] = None,
    min_flow_pct: Annotated[
        Optional[float],
        typer.Option("--min-flow-pct", help="Require average foreign flow percent"),
    ] = None,
    require_rsi: Annotated[
        bool,
        typer.Option("--require-rsi", help="Exclude signals with missing RSI"),
    ] = False,
    max_rsi: Annotated[
        Optional[float],
        typer.Option("--max-rsi", help="Require RSI at or below this value"),
    ] = None,
    simulate_exits: Annotated[
        Optional[bool],
        typer.Option("--simulate-exits", help="Run TP/SL/max-hold exit grid"),
    ] = None,
    take_profits: Annotated[
        Optional[str],
        typer.Option("--take-profits", help="Comma-separated take-profit percentages"),
    ] = None,
    stop_losses: Annotated[
        Optional[str],
        typer.Option("--stop-losses", help="Comma-separated stop-loss percentages"),
    ] = None,
    max_holds: Annotated[
        Optional[str],
        typer.Option("--max-holds", help="Comma-separated max holding days"),
    ] = None,
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Forward horizon for max up/down metrics", min=5),
    ] = 20,
    output_path: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Write raw audit records to CSV"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    top_groups: Annotated[
        int,
        typer.Option("--top-groups", help="Number of grouped summary rows to print", min=1),
    ] = 80,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Replay accumulation signals historically and measure forward returns.

    This command is deterministic and offline. It uses cached local candles and
    broker summaries only; run `saham update --universe <name>` first.
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    preset_name = preset.lower() if preset else None
    preset_values = {}
    if preset_name is not None:
        if preset_name not in AUDIT_PRESETS:
            typer.echo(
                f"Error: unknown preset '{preset}'. "
                f"Available presets: {', '.join(AUDIT_PRESETS)}",
                err=True,
            )
            raise typer.Exit(1)
        preset_values = AUDIT_PRESETS[preset_name]

    universe = universe or preset_values.get("universe")
    window = window if window is not None else int(preset_values.get("window", 7))
    min_score = (
        min_score if min_score is not None
        else float(preset_values.get("min_score", 40.0))
    )
    min_net_buy_days = (
        min_net_buy_days if min_net_buy_days is not None
        else int(preset_values.get("min_net_buy_days", 2))
    )
    min_vwap_disc = (
        min_vwap_disc if min_vwap_disc is not None
        else preset_values.get("min_vwap_disc")
    )
    trend = trend or preset_values.get("trend")
    min_flow_pct = (
        min_flow_pct if min_flow_pct is not None
        else preset_values.get("min_flow_pct")
    )
    require_rsi = require_rsi or bool(preset_values.get("require_rsi", False))
    max_rsi = max_rsi if max_rsi is not None else preset_values.get("max_rsi")
    simulate_exits = (
        simulate_exits if simulate_exits is not None
        else bool(preset_values.get("simulate_exits", False))
    )
    take_profits = take_profits or str(preset_values.get("take_profits", "4,5,6"))
    stop_losses = stop_losses or str(preset_values.get("stop_losses", "3,5,7"))
    max_holds = max_holds or str(preset_values.get("max_holds", "3,5,7,10"))

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
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
            "No tickers to audit. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    trend_filter = trend.upper() if trend else None
    if trend_filter is not None and trend_filter not in {"UP", "SIDE", "DOWN"}:
        typer.echo("Error: --trend must be one of: UP, SIDE, DOWN", err=True)
        raise typer.Exit(1)

    filter_parts = []
    if min_vwap_disc is not None:
        filter_parts.append(f"VWAP>={min_vwap_disc:g}%")
    if trend_filter is not None:
        filter_parts.append(f"trend={trend_filter}")
    if min_flow_pct is not None:
        filter_parts.append(f"flow>={min_flow_pct:g}%")
    if require_rsi:
        filter_parts.append("RSI present")
    if max_rsi is not None:
        filter_parts.append(f"RSI<={max_rsi:g}")
    if simulate_exits:
        filter_parts.append("exit simulation")
    filter_label = f" | filters: {', '.join(filter_parts)}" if filter_parts else ""

    try:
        take_profit_grid = _parse_float_grid(take_profits, "--take-profits")
        stop_loss_grid = _parse_float_grid(stop_losses, "--stop-losses")
        max_hold_grid = _parse_int_grid(max_holds, "--max-holds")
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format != "json":
        typer.echo(
            f"Auditing {len(ticker_list)} tickers | {start_date} to {end_date} | "
            f"{window} sessions | min score {min_score:g}{filter_label}..."
        )

    use_case = AccumulationAuditUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            window_days=window,
            min_net_buy_days=min_net_buy_days,
            min_score=min_score,
            horizon_days=horizon,
            min_vwap_disc_pct=min_vwap_disc,
            trend=trend_filter,
            min_flow_pct=min_flow_pct,
            require_rsi=require_rsi,
            max_rsi=max_rsi,
            simulate_exits=simulate_exits,
            take_profit_pcts=take_profit_grid,
            stop_loss_pcts=stop_loss_grid,
            max_hold_days=max_hold_grid,
        )
    )

    if output_path is not None:
        _write_audit_csv(response, output_path)
        typer.echo(f"Wrote {response.total_records} audit records to {output_path}")

    if output_format == "json":
        typer.echo(json.dumps({
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "window_days": response.window_days,
            "total_replay_dates": response.total_replay_dates,
            "total_tickers": response.total_tickers,
            "total_records": response.total_records,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "warnings": response.warnings,
            "group_stats": [s.to_dict() for s in response.group_stats],
            "exit_simulations": [s.to_dict() for s in response.exit_simulations],
        }, indent=2, default=str))
        return

    _display_audit_summary(response, top_groups=top_groups)


# ---------------------------------------------------------------------------
# Universe management commands
# ---------------------------------------------------------------------------

@universe_app.command("list")
def universe_list(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    List configured ticker universes with last-updated date and ticker count.

    Example:
        saham universe list
    """
    from src.application.services.universe_loader import UNIVERSE_CONFIG_PATH

    resolved_config = config_path or UNIVERSE_CONFIG_PATH
    meta = load_universe_meta(resolved_config)

    if not meta:
        typer.echo(f"No universe config found at '{resolved_config}'.")
        typer.echo("Expected: config/universes.yaml")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Configured universes:")
    typer.echo(f"  {'NAME':<14} {'TICKERS':>8}  {'LAST UPDATED'}")
    typer.echo("  " + "-" * 40)
    for name, info in meta.items():
        typer.echo(f"  {name:<14} {info['count']:>8}  {info['updated']}")
    typer.echo("")
    typer.echo(f"Config file: {resolved_config}")
    typer.echo("")
    typer.echo("Usage: saham data update --universe <name>")
    typer.echo("       saham trade swing screen --universe <name>")


@universe_app.command("update")
def universe_update(
    universe_name: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe to update (lq45, idx80, idxcomp100)"),
    ] = None,
) -> None:
    """
    Refresh universe ticker lists from IDX website.

    Currently prints instructions — automatic scraping from IDX
    will be implemented in a future release.

    Example:
        saham universe update --universe lq45
    """
    typer.echo("")
    typer.echo("Universe auto-update from IDX website is not yet implemented.")
    typer.echo("")
    typer.echo("To update manually:")
    typer.echo("  1. Visit https://www.idx.co.id/en/market-data/indexes/")
    typer.echo("  2. Download the latest LQ45 / IDX80 constituent list")
    typer.echo("  3. Edit config/universes.yaml with the new tickers")
    typer.echo("  4. Update the 'updated' date field")
    typer.echo("")
    typer.echo("IDX rebalances indices every February and August.")


# ---------------------------------------------------------------------------
# Accumulation trade journal commands
# ---------------------------------------------------------------------------

DEFAULT_ACCUM_JOURNAL_PATH = Path("journals/accumulation.csv")


def accumulation_log(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Ticker symbol to log (e.g. BBRI)"),
    ],
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (default = latest close)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record preset decision, failed gates, and trade plan fields",
        ),
    ] = False,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to journal with --from-analysis"),
    ] = FOREIGN_BOUNCE_PRESET,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label in journal row"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log an accumulation candidate to the trade journal.

    Runs the accumulation screen for TICKER and appends one row to the
    journal CSV. Idempotent: re-running for the same (date, ticker, window)
    never duplicates rows.

    Example:
        saham swing log --ticker BBRI --window 7
        saham swing log --ticker BBCA --entry-price 9450
        saham swing log --ticker BBRI --from-analysis --with-regime
    """
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )

    resolved_db = db_path or DEFAULT_DB_PATH
    journal_path = journal or DEFAULT_ACCUM_JOURNAL_PATH
    ticker_upper = ticker.upper()
    logged_at = date.today()
    preset_name = preset.lower()
    if from_analysis and preset_name != FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. Available presets: {FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    _corp_repo, _season_prov = _make_stockbit_providers(resolved_db)

    # Run single-ticker screen to get candidate
    use_case = AccumulationScreenUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
        corporate_action_repo=_corp_repo,
        seasonality_provider=_season_prov,
    )
    response = use_case.execute(AccumulationScreenRequest(
        tickers=[ticker_upper],
        window_days=window,
        min_score=0.0,
        min_net_buy_days=0,
        tier1_broker_codes=_SC.tier1_broker_codes,
    ))
    candidate = next((c for c in response.candidates if c.ticker == ticker_upper), None)

    # Compute multi-window pattern (7, 30, 90)
    pattern: str | None = None
    try:
        windows = [7, 30, 90]
        multi = {
            w: use_case.execute(AccumulationScreenRequest(
                tickers=[ticker_upper],
                window_days=w,
                min_score=0.0,
                min_net_buy_days=0,
                tier1_broker_codes=_SC.tier1_broker_codes,
            ))
            for w in windows
        }
        candidates_by_window = {
            w: next((c for c in resp.candidates if c.ticker == ticker_upper), None)
            for w, resp in multi.items()
        }
        pattern = _classify_pattern(windows, candidates_by_window)
    except Exception:
        pass  # pattern stays None if multi-window fails

    # Resolve entry price
    resolved_entry: Decimal
    if entry_price is not None:
        resolved_entry = Decimal(str(entry_price))
    elif candidate is not None:
        # Use latest close from candles
        try:
            today = date.today()
            candles = market_repo.get_candles(
                ticker_upper,
                start_date=today.replace(month=1, day=1),
                end_date=today,
            )
            resolved_entry = candles[-1].close if candles else Decimal("0")
        except Exception:
            resolved_entry = Decimal("0")
    else:
        typer.echo(
            f"Warning: no accumulation data for {ticker_upper} in the last {window} broker sessions. "
            "Logging with score=0.",
            err=True,
        )
        resolved_entry = Decimal("0")

    classification: str | None = None
    failed_gates: tuple[str, ...] = ()
    planned_entry: Decimal | None = None
    planned_stop: Decimal | None = None
    planned_target: Decimal | None = None
    max_hold_days: int | None = None
    regime: str | None = None
    journal_preset: str | None = None

    if from_analysis:
        journal_preset = preset_name
        classification, failed_gates = _foreign_bounce_decision(candidate)
        planned_entry = resolved_entry
        planned_stop, planned_target = _percent_plan(resolved_entry)
        max_hold_days = FOREIGN_BOUNCE_MAX_HOLD_DAYS

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
                regime_response = regime_uc.execute(MarketRegimeRequest(
                    universe=regime_tickers,
                    benchmark_ticker=benchmark,
                    as_of_date=logged_at,
                ))
                regime = regime_response.label
            except Exception as exc:
                typer.echo(
                    f"Warning: could not compute market regime for journal row: {exc}",
                    err=True,
                )

    store = AccumulationJournalCsvWriter(journal_path)
    service = AccumulationJournalService(store=store, repository=market_repo)

    count = service.log_candidate(
        ticker=ticker_upper,
        entry_price=resolved_entry,
        window_days=window,
        candidate=candidate,
        logged_at=logged_at,
        pattern=pattern,
        preset=journal_preset,
        classification=classification,
        failed_gates=failed_gates,
        regime=regime,
        planned_entry=planned_entry,
        planned_stop=planned_stop,
        planned_target=planned_target,
        max_hold_days=max_hold_days,
    )

    if count == 0:
        typer.echo(
            f"Already logged {ticker_upper} for {logged_at} (window={window} sessions) — "
            f"no new row added ({journal_path})"
        )
    else:
        score_str = f"{candidate.score:.1f}" if candidate else "0.0"
        pattern_str = f" | pattern: {pattern}" if pattern else ""
        decision_str = (
            f" | preset={journal_preset} | decision={classification}"
            if from_analysis
            else ""
        )
        plan_str = (
            f" | plan entry={planned_entry:,.0f} stop={planned_stop:,.0f} "
            f"target={planned_target:,.0f} hold={max_hold_days}d"
            if from_analysis
            and planned_entry is not None
            and planned_stop is not None
            and planned_target is not None
            and max_hold_days is not None
            else ""
        )
        regime_str = f" | regime={regime}" if regime else ""
        typer.echo(
            f"Logged {ticker_upper} | {logged_at} | window={window} sessions | "
            f"score={score_str}{pattern_str}{decision_str}{regime_str}{plan_str} → {journal_path}"
        )
        if from_analysis and failed_gates:
            typer.echo("Failed gates:")
            for gate in failed_gates:
                typer.echo(f"  - {gate}")


def accumulation_review(
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Trading days forward for max/min window", min=1),
    ] = 10,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Only include entries with score ≥ this"),
    ] = 0.0,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Review accumulation trade journal: forward returns by score and pattern.

    Fetches actual forward closes from the local database and computes
    what the accumulation score thresholds actually delivered.

    Example:
        saham swing review
        saham swing review --horizon 10 --min-score 70
    """
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )

    journal_path = journal or DEFAULT_ACCUM_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham swing log --ticker BBRI` first.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    store = AccumulationJournalCsvWriter(journal_path)
    service = AccumulationJournalService(store=store, repository=market_repo)

    typer.echo(f"Reviewing journal ({journal_path}) | horizon={horizon}d ...")
    report = service.review(horizon_days=horizon)

    _W = 70

    typer.echo("")
    typer.echo("=" * _W)
    typer.echo("ACCUMULATION TRADE JOURNAL REVIEW")
    typer.echo("=" * _W)
    typer.echo(f"Journal  : {journal_path}")
    typer.echo(f"Entries  : {report.total_entries} total | {report.enriched_entries} with {horizon}d+ data")
    typer.echo(f"Horizon  : {horizon} trading days | min_score filter: {min_score}")

    if report.enriched_entries == 0:
        typer.echo("")
        typer.echo("No enriched entries yet — check back after market data covers the horizon.")
        typer.echo("=" * _W)
        return

    # Apply min_score filter to the enriched entries for display
    # (report already computed; we just filter display)
    def _pct(v: float | None) -> str:
        return f"{v:+.1f}%" if v is not None else "  N/A"

    def _wr(v: float | None) -> str:
        return f"{v:.0f}%" if v is not None else " N/A"

    # ── PERFORMANCE BY SCORE BUCKET ──
    typer.echo("")
    typer.echo(typer.style("PERFORMANCE BY SCORE BUCKET", fg=typer.colors.CYAN, bold=True))
    typer.echo(f"  {'BUCKET':<10} {'N':>4}  {'AVG_5D':>8}  {'AVG_10D':>8}  {'WIN_RATE_10D':>13}")
    typer.echo("  " + "-" * 50)
    for stat in report.score_buckets:
        if stat.n == 0 and min_score > 0:
            continue
        typer.echo(
            f"  {stat.bucket:<10} {stat.n:>4}  {_pct(stat.avg_return_5d):>8}  "
            f"{_pct(stat.avg_return_10d):>8}  {_wr(stat.win_rate_10d):>13}"
        )

    # ── PERFORMANCE BY PRESET DECISION ──
    if report.by_decision:
        typer.echo("")
        typer.echo(typer.style("PERFORMANCE BY PRESET DECISION", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'DECISION':<12} {'N':>4}  {'AVG_10D':>8}  {'WIN_RATE':>9}  "
            f"{'AVG_MAX_UP':>11}  {'AVG_MAX_DD':>11}"
        )
        typer.echo("  " + "-" * 62)
        for stat in report.by_decision:
            typer.echo(
                f"  {stat.decision:<12} {stat.n:>4}  {_pct(stat.avg_return_10d):>8}  "
                f"{_wr(stat.win_rate_10d):>9}  {_pct(stat.avg_max_upside):>11}  "
                f"{_pct(stat.avg_max_drawdown):>11}"
            )

    # ── PERFORMANCE BY PATTERN ──
    if report.by_pattern:
        typer.echo("")
        typer.echo(typer.style("PERFORMANCE BY PATTERN", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'PATTERN':<18} {'N':>4}  {'AVG_10D':>8}  {'WIN_RATE':>9}  "
            f"{'AVG_MAX_UP':>11}  {'AVG_MAX_DD':>11}"
        )
        typer.echo("  " + "-" * 70)
        for stat in report.by_pattern:
            typer.echo(
                f"  {stat.pattern:<18} {stat.n:>4}  {_pct(stat.avg_return_10d):>8}  "
                f"{_wr(stat.win_rate_10d):>9}  {_pct(stat.avg_max_upside):>11}  "
                f"{_pct(stat.avg_max_drawdown):>11}"
            )

    # ── SIGNAL DELTA ──
    if report.signal_deltas:
        typer.echo("")
        typer.echo(typer.style("SIGNAL DELTA (correlation with 10d return)", fg=typer.colors.CYAN, bold=True))
        typer.echo(
            f"  {'SIGNAL':<12}  {'GROUP A':<20}  {'N_A':>4}  {'AVG_A':>7}  "
            f"{'GROUP B':<20}  {'N_B':>4}  {'AVG_B':>7}"
        )
        typer.echo("  " + "-" * 82)
        for d in report.signal_deltas:
            typer.echo(
                f"  {d.signal:<12}  {d.group_a_label:<20}  {d.group_a_n:>4}  "
                f"{_pct(d.group_a_avg_10d):>7}  {d.group_b_label:<20}  "
                f"{d.group_b_n:>4}  {_pct(d.group_b_avg_10d):>7}"
            )

    typer.echo("")
    typer.echo("Note: 20+ entries needed for statistically meaningful results.")
    typer.echo("DISCLAIMER: Past performance does not predict future returns.")
    typer.echo("=" * _W)
