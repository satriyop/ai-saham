"""
CLI commands for the intraday trading command family.

Usage patterns:

  # Autonomous (playwright + saved session):
  saham intraday pre-open

  # Fast mode (no order book, ~15s):
  saham intraday pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

  # Normal mode with order book data:
  saham intraday pre-open \\
    --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
    --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

  # Paper trade journal:
  saham intraday pre-open-log
  saham intraday pre-open-review --horizon 5

Layer: Adapter
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional
from zoneinfo import ZoneInfo

import typer
import yaml

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.assess_risk import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.intraday_backtest import (
    IntradayBacktestRequest,
    IntradayBacktestResponse,
    IntradayBacktestUseCase,
)
from src.application.use_case.confirm_intraday_open import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.application.use_case.pre_open_screen import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.ports.browser_data_provider import BrowserInteractionRequired
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmation,
    IntradayConfirmationCandidate,
    IntradayConfirmationJournalEntry,
)
from src.domain.value_objects.screener_result import ScreenerCandidate
from src.infrastructure.browser.stockbit_browser import (
    ManualBrowserDataProvider,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

intraday_app = typer.Typer(
    name="intraday",
    help="Intraday screening, confirmation, journal, and audit workflow",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_PRE_OPEN_CONFIG_PATH = Path("config/pre_open_screener.yaml")
DEFAULT_SESSION_FILE = Path("stockbit_session.json")
DEFAULT_SIDECAR_PATH = Path("journals/.last-session.json")
DEFAULT_CONFIRMATION_PATH = Path("journals/.last-confirmation.json")
DEFAULT_CONFIRMATION_JOURNAL_PATH = Path("journals/intraday-confirmations.csv")
DEFAULT_JOURNAL_PATH = Path("journals/pre-open.csv")
DEFAULT_REGIME_UNIVERSE = "idx80"
DEFAULT_REGIME_BENCHMARK = "^JKSE"
IDX_TIMEZONE = ZoneInfo("Asia/Jakarta")
PRE_OPEN_START = time(8, 45)
PRE_OPEN_END = time(9, 0)


@dataclass(frozen=True)
class IntradayRunGuard:
    """Runtime guard for pre-open workflow timing."""

    run_at: datetime
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class IntradayDataFreshness:
    """Data-source dates used by the pre-open screen."""

    analysis_date: date
    candle_end: date | None
    broker_end: date | None
    warnings: tuple[str, ...] = ()


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _session_exists() -> bool:
    return DEFAULT_SESSION_FILE.exists()


def _current_idx_datetime() -> datetime:
    return datetime.now(IDX_TIMEZONE)


def _build_intraday_run_guard(
    run_at: datetime,
    allow_non_trading_day: bool = False,
) -> IntradayRunGuard:
    """Build deterministic timing warnings/errors for the pre-open workflow."""
    warnings: list[str] = []

    local_run_at = run_at.astimezone(IDX_TIMEZONE)
    if local_run_at.weekday() >= 5:
        message = (
            f"{local_run_at.date()} is a weekend in Asia/Jakarta. "
            "Use --allow-non-trading-day only for dry-runs/backfills."
        )
        if not allow_non_trading_day:
            return IntradayRunGuard(run_at=local_run_at, error=message)
        warnings.append(message)

    current_time = local_run_at.time()
    if not (PRE_OPEN_START <= current_time < PRE_OPEN_END):
        warnings.append(
            "Current Asia/Jakarta time is outside IDX pre-open window "
            f"{PRE_OPEN_START.strftime('%H:%M')}-{PRE_OPEN_END.strftime('%H:%M')}."
        )

    return IntradayRunGuard(run_at=local_run_at, warnings=tuple(warnings))


def _load_config(config_path: Path, overrides: dict) -> PreOpenScreenConfig:
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        config = PreOpenScreenConfig.from_yaml(data)
    else:
        config = PreOpenScreenConfig()

    if overrides.get("iev_min") is not None:
        config.iev_min = overrides["iev_min"]
    if overrides.get("iep_min") is not None:
        config.iep_min = overrides["iep_min"]
    if overrides.get("capital") is not None:
        config.capital = Decimal(str(overrides["capital"]))
    if overrides.get("stop_loss_pct") is not None:
        config.stop_loss_pct = Decimal(str(overrides["stop_loss_pct"]))
    if overrides.get("tick_above") is not None:
        config.tick_above = overrides["tick_above"]
    if overrides.get("top_n") is not None:
        config.top_n = overrides["top_n"]
    if overrides.get("fast_mode") is not None:
        config.fast_mode = overrides["fast_mode"]
    if overrides.get("max_gap") is not None:
        config.max_gap_pct = Decimal(str(overrides["max_gap"]))
    if overrides.get("atr_mult") is not None:
        config.atr_multiplier = Decimal(str(overrides["atr_mult"]))

    return config


def _min_latest_date(dates: list[date]) -> date | None:
    if not dates:
        return None
    return min(dates)


def _build_data_freshness(
    candidates: list[ScreenerCandidate],
    analysis_date: date,
    market_repo: SQLiteMarketRepository,
    broker_repo: SQLiteBrokerRepository,
) -> IntradayDataFreshness:
    tickers = sorted({c.ticker.upper() for c in candidates})
    candle_dates: list[date] = []
    broker_dates: list[date] = []

    for ticker in tickers:
        candle_range = market_repo.get_date_range(ticker)
        if candle_range:
            candle_dates.append(candle_range[1])
        broker_range = broker_repo.get_date_range(ticker)
        if broker_range:
            broker_dates.append(broker_range[1])

    candle_end = _min_latest_date(candle_dates)
    broker_end = _min_latest_date(broker_dates)
    warnings: list[str] = []

    if candle_end is None:
        warnings.append("No cached candle date found for screened candidates.")
    elif candle_end < analysis_date:
        lag = (analysis_date - candle_end).days
        warnings.append(
            f"Latest candle date is {candle_end}, {lag} calendar day(s) before analysis date."
        )

    if broker_end is None:
        warnings.append("No cached broker-flow date found for screened candidates.")
    elif broker_end < analysis_date:
        lag = (analysis_date - broker_end).days
        warnings.append(
            f"Latest broker-flow date is {broker_end}, {lag} calendar day(s) before analysis date."
        )

    if candle_end and broker_end and candle_end != broker_end:
        warnings.append(
            f"Candle and broker-flow dates differ ({candle_end} vs {broker_end})."
        )

    return IntradayDataFreshness(
        analysis_date=analysis_date,
        candle_end=candle_end,
        broker_end=broker_end,
        warnings=tuple(warnings),
    )


def _display_data_freshness(freshness: IntradayDataFreshness | None) -> None:
    if freshness is None:
        return

    candle = freshness.candle_end.isoformat() if freshness.candle_end else "N/A"
    broker = freshness.broker_end.isoformat() if freshness.broker_end else "N/A"
    typer.echo("")
    typer.echo(
        "DATA: "
        f"Analysis date {freshness.analysis_date.isoformat()}   "
        f"Candles through {candle}   "
        f"Broker flow through {broker}"
    )


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    sign = "+" if signed else ""
    return f"{value:{sign}.2f}%"


def _format_market_regime(response: MarketRegimeResponse) -> str:
    return (
        f"REGIME: {response.label} score={response.score}/7   "
        f"{response.benchmark_ticker} 20d {_fmt_pct(response.benchmark_return_20d_pct, True)}   "
        f"Breadth SMA20 {_fmt_pct(response.breadth_above_sma20_pct)}   "
        f"Foreign breadth {_fmt_pct(response.foreign_flow_breadth_pct)}"
    )


def _market_regime_warning(response: MarketRegimeResponse) -> str | None:
    if response.label == "RISK_OFF":
        return "Market regime is RISK_OFF; avoid marginal long scalps or cut size."
    if response.label == "WEAK":
        return "Market regime is WEAK; require cleaner opening confirmation or reduce size."
    return None


def _build_market_regime(
    market_repo: SQLiteMarketRepository,
    broker_repo: SQLiteBrokerRepository,
    db_path: Path,
    as_of_date: date,
    universe: str,
    benchmark: str,
) -> MarketRegimeResponse:
    tickers = resolve_tickers(
        universe=universe,
        explicit=[],
        db_path=db_path,
    )
    use_case = MarketRegimeUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
    )
    return use_case.execute(
        MarketRegimeRequest(
            universe=tickers,
            benchmark_ticker=benchmark,
            as_of_date=as_of_date,
        )
    )


def _display_market_regime(response: MarketRegimeResponse | None) -> None:
    if response is None:
        return
    typer.echo(_format_market_regime(response))


def _display_raw_movers(raw_movers: list, top_n: int | None, iev_min: int) -> None:
    """Print a compact summary of all movers fetched from IEV API before screener filtering."""
    if not raw_movers:
        return
    total = len(raw_movers)
    shown = top_n if top_n else total
    cap = min(shown, total)

    typer.echo("")
    typer.echo(f"Fetched {total} movers from Stockbit (top {cap} screened):")

    # Two rows of up to 10 tickers each, compact format
    tickers_with_iev = []
    for mover in raw_movers[:20]:
        iep_suffix = f" @{mover.iep:,}" if mover.iep is not None else ""
        tickers_with_iev.append(f"{mover.ticker} {mover.iev / 1000:.0f}K{iep_suffix}")
    row1 = "  " + "  |  ".join(tickers_with_iev[:10])
    typer.echo(row1)
    if len(tickers_with_iev) > 10:
        row2 = "  " + "  |  ".join(tickers_with_iev[10:])
        typer.echo(row2)
    if total > 20:
        typer.echo(f"  ... and {total - 20} more below threshold")
    typer.echo("")


_VERDICT_ORDER = {"PRIME": 0, "WATCH": 1, "NO_DATA": 2, "SKIP": 3}


def _verdict(c: "ScreenerCandidate") -> str:
    """Synthesise all signals into a single action verdict."""
    if c.entry_range_low is None:
        return "NO_DATA"
    if c.trend_signal == "BEARISH" or c.accum_tag == "DISTRIBUTING":
        return "SKIP"
    if c.trend_signal == "NEUTRAL":
        return "SKIP"
    # BULLISH from here
    backed = c.accum_tag == "BACKED"
    floor = c.fvwap_discount_pct is not None and c.fvwap_discount_pct > 0
    if backed and floor:
        return "PRIME"
    return "WATCH"


def _signal_col(c: "ScreenerCandidate") -> str:
    """Compact ACCUM tag + FVWAP into a single SIGNAL string."""
    parts: list[str] = []
    if c.accum_tag is not None:
        tag = c.accum_tag[:8]  # truncate UNCONFIRMED → UNCONFIRM
        streak = f"×{c.accum_streak}d" if c.accum_streak else ""
        parts.append(f"{tag}{streak}")
    if c.fvwap_discount_pct is not None:
        note = " floor" if c.fvwap_discount_pct > 0 else (" sell" if c.fvwap_discount_pct < -3 else "")
        parts.append(f"{c.fvwap_discount_pct:+.1f}%{note}")
    if c.prev_high:
        parts.append(f"PH:{c.prev_high:,.0f}")
    return "  ".join(parts) if parts else "—"


def _print_browser_plan(config: PreOpenScreenConfig) -> None:
    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("BROWSER ACTION PLAN — Pre-Open Screener")
    typer.echo("=" * 60)
    typer.echo("")
    typer.echo("Claude Code: execute these steps, then re-run this command")
    typer.echo("with --movers-json and --order-books-json flags.")
    typer.echo("")
    typer.echo("STEP 1 — Fetch IEV Movers from Stockbit")
    typer.echo("-" * 40)
    typer.echo("  URL: https://stockbit.com/#/screener")
    typer.echo('  1. Go to Screener → Movers section, click "Selengkapnya"')
    typer.echo("  2. Sort by IEV column, descending")
    top_label = f"top {config.top_n}" if config.top_n else "all rows"
    typer.echo(f"  3. Collect {top_label} with IEV >= {config.iev_min:,}")
    typer.echo("  4. Build JSON array:")
    typer.echo('     [{"ticker": "BBCA", "iev": 150000}, ...]')
    typer.echo("")
    if not config.fast_mode:
        typer.echo("STEP 2 — Fetch Order Books (for each ticker from Step 1)")
        typer.echo("-" * 40)
        typer.echo("  URL: https://stockbit.com/#/stock/{TICKER}/orderbook")
        typer.echo("  1. For each ticker: open order book tab")
        typer.echo("  2. Find the BID row with the LARGEST volume (lots)")
        typer.echo("  3. Record price and volume")
        typer.echo("  4. Build JSON object:")
        typer.echo('     {"BBCA": {"price": 8900, "volume": 50000}, ...}')
        typer.echo("")
        typer.echo("STEP 3 — Re-run with collected data")
        typer.echo("-" * 40)
        typer.echo("  saham intraday pre-open \\")
        typer.echo("    --movers-json '<step1_json>' \\")
        typer.echo("    --order-books-json '<step2_json>'")
    else:
        typer.echo("STEP 2 — Re-run with movers data (fast mode — no order book needed)")
        typer.echo("-" * 40)
        typer.echo("  saham intraday pre-open --fast --movers-json '<step1_json>'")
    typer.echo("")
    typer.echo("=" * 60)


_STRAT_SYMBOL = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}
_STRAT_COLOR  = {
    "LOW_RISK":  typer.colors.GREEN,
    "HIGH_RISK": typer.colors.RED,
    "MODERATE":  typer.colors.BRIGHT_BLACK,
}


def _display_results(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: IntradayDataFreshness | None = None,
    market_regime: MarketRegimeResponse | None = None,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    typer.echo("")
    typer.echo("=" * 90)
    typer.echo("PRE-OPEN SCREENER RESULTS")
    typer.echo("=" * 90)
    typer.echo(f"Date: {screened_date}   IEV filter: >= {iev_min:,}")
    typer.echo(f"Movers evaluated: {total_movers_seen}   Candidates: {len(candidates)}")
    _display_data_freshness(data_freshness)
    _display_market_regime(market_regime)
    typer.echo("")

    if not candidates:
        typer.echo("No candidates passed the IEV filter.")
        typer.echo("=" * 90)
        return

    # Sort: PRIME → WATCH → NO_DATA → SKIP, then by IEV descending within group
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (_VERDICT_ORDER.get(_verdict(c), 99), -c.iev),
    )

    # Header — compact 1-row-per-ticker layout
    show_spread = any(c.spread_pct is not None for c in sorted_candidates)
    strat_header = f"  {'STRAT':>5}" if strategy_signals else ""
    sprd_header = f"  {'SPRD%':>6}" if show_spread else ""
    sep_width = 90 + (8 if strategy_signals else 0) + (9 if show_spread else 0)
    header = (
        f"{'VERDICT':<10} {'TICKER':<7} {'IEV':>7}  {'GAP%':>6}"
        f"{sprd_header}  "
        f"{'ENTRY-RANGE':>16}  {'STOP%':>6}  {'RSI':>4}  {'SIGNAL'}"
        f"{strat_header}"
    )
    typer.echo(header)
    typer.echo("-" * sep_width)

    _VERDICT_STYLE = {
        "PRIME":   (typer.colors.GREEN,       True,  "★ PRIME  "),
        "WATCH":   (typer.colors.YELLOW,      False, "◉ WATCH  "),
        "NO_DATA": (typer.colors.BRIGHT_BLACK, False, "? NO_DATA"),
        "SKIP":    (typer.colors.RED,         False, "✗ SKIP   "),
    }

    for c in sorted_candidates:
        v = _verdict(c)
        color, bold, label = _VERDICT_STYLE.get(v, (typer.colors.WHITE, False, v))
        verdict_str = typer.style(label, fg=color, bold=bold)

        gap = c.gap_label
        sprd_col = f"  {c.spread_label:>6}" if show_spread else ""
        rng = c.entry_range_label
        stop_pct = c.risk_reward_label
        rsi_str = f"{float(c.rsi):.0f}" if c.rsi else "—"
        signal = _signal_col(c)

        strat_col = ""
        if strategy_signals is not None:
            raw = strategy_signals.get(c.ticker, "?")
            sym = _STRAT_SYMBOL.get(raw, raw)
            col = _STRAT_COLOR.get(raw, typer.colors.WHITE)
            strat_col = "  " + typer.style(f"{sym:>5}", fg=col, bold=(raw == "LOW_RISK"))

        typer.echo(
            f"{verdict_str} {c.ticker:<7} {c.iev:>7,}  {gap:>6}"
            f"{sprd_col}  "
            f"{rng:>16}  {stop_pct:>6}  {rsi_str:>4}  {signal}{strat_col}"
        )

    typer.echo("-" * sep_width)

    # AI summaries (if any)
    has_ai = any(c.ai_summary for c in sorted_candidates)
    if has_ai:
        typer.echo("")
        typer.echo("AI RESEARCH SUMMARIES")
        typer.echo("-" * 90)
        for c in sorted_candidates:
            if c.ai_summary:
                typer.echo(f"\n[{c.ticker}]")
                typer.echo(c.ai_summary)

    all_warnings = list(warnings)
    if data_freshness is not None:
        all_warnings.extend(data_freshness.warnings)
    if market_regime is not None:
        all_warnings.extend(market_regime.warnings)
        regime_warning = _market_regime_warning(market_regime)
        if regime_warning:
            all_warnings.append(regime_warning)

    if all_warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for w in all_warnings:
            typer.echo(f"  ! {w}")

    # Action summary — watchlist + ready-to-run confirm-open command
    watchlist = [c for c in sorted_candidates if _verdict(c) in ("PRIME", "WATCH")]
    skipped   = [c for c in sorted_candidates if _verdict(c) not in ("PRIME", "WATCH")]

    typer.echo("")
    typer.echo("━" * 60)
    if watchlist:
        watch_labels = []
        for c in watchlist:
            prefix = "★" if _verdict(c) == "PRIME" else "◉"
            watch_labels.append(f"{prefix} {c.ticker}")
        skip_labels = "  ".join(c.ticker for c in skipped) or "—"
        typer.echo(
            " WATCHLIST  " + typer.style("  ".join(watch_labels), fg=typer.colors.GREEN, bold=True)
        )
        typer.echo(
            " SKIP       " + typer.style(skip_labels, fg=typer.colors.BRIGHT_BLACK)
        )
        # Build confirm-open command template
        tickers_json = ",".join(f'"{c.ticker}":___' for c in watchlist)
        typer.echo("")
        typer.echo(" At 09:00, fill opening prices and run:")
        typer.echo(
            typer.style(
                f"   saham intraday confirm-open \\\n"
                f"     --opening-json '{{{tickers_json}}}'",
                fg=typer.colors.CYAN,
            )
        )
    else:
        typer.echo(" No candidates meet criteria today.")
        typer.echo(" Consider: --iev-min 50000 or check 'saham stockbit fetch-top5'")
    typer.echo("━" * 60)

    typer.echo("")
    typer.echo(
        "VERDICT: ★ PRIME=all signals green  ◉ WATCH=bullish, needs confirm  "
        "✗ SKIP=bearish/distributing  ? NO_DATA=run 'saham update TICKER --days 365'"
    )
    typer.echo(
        "SIGNAL: ACCUM tag × streak  |  FVWAP% (floor=asing underwater, sell=asing profit)  |  PH=Prev High"
    )
    typer.echo("STOP%: max loss from entry (ATR-based, capped -7%)")
    if strategy_signals is not None:
        typer.echo(
            f"STRAT ({strategy_name}): ↑=LOW_RISK(entry)  ~=MODERATE(hold)  ↓=HIGH_RISK(exit)"
        )
    typer.echo("")
    typer.echo("DISCLAIMER: Analysis only. Not trading advice.")
    typer.echo("=" * 90)


def _write_sidecar(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    sidecar_path: Path,
    market_regime: MarketRegimeResponse | None = None,
) -> None:
    """Write session sidecar JSON so `saham intraday pre-open-log` can read it."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "screened_at": str(screened_date),
        "market_regime": market_regime.to_dict() if market_regime else None,
        "candidates": [
            {
                "ticker": c.ticker,
                "iev": c.iev,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "entry_range_low": str(c.entry_range_low) if c.entry_range_low else None,
                "entry_range_high": str(c.entry_range_high) if c.entry_range_high else None,
                "suggested_entry": str(c.entry_price) if c.entry_price else None,
                "atr_stop": str(c.stop_loss_price) if c.stop_loss_price else None,
                "trend": c.trend_signal,
                "rsi": str(c.rsi) if c.rsi else None,
                "accum_tag": c.accum_tag,
                "accum_score": c.accum_score,
                "accum_streak": c.accum_streak,
                "foreign_vwap": str(c.foreign_vwap) if c.foreign_vwap else None,
                "fvwap_discount_pct": (
                    c.fvwap_discount_pct if c.fvwap_discount_pct is not None else None
                ),
                "prev_high": float(c.prev_high) if c.prev_high else None,
                "prev_low": float(c.prev_low) if c.prev_low else None,
            }
            for c in candidates
        ],
    }
    with open(sidecar_path, "w") as f:
        json.dump(data, f, indent=2)


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _load_confirmation_candidates(
    session_path: Path,
    opening_prices: dict[str, Decimal],
) -> tuple[date, list[IntradayConfirmationCandidate], dict[str, dict]]:
    with open(session_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])
    candidates: list[IntradayConfirmationCandidate] = []
    extras: dict[str, dict] = {}  # {ticker: {prev_high, prev_low, entry_range_low}}

    for row in data.get("candidates", []):
        ticker = str(row["ticker"]).upper()
        candidates.append(
            IntradayConfirmationCandidate(
                ticker=ticker,
                opening_price=opening_prices.get(ticker),
                iev=row.get("iev"),
                entry_range_low=_decimal_or_none(row.get("entry_range_low")),
                entry_range_high=_decimal_or_none(row.get("entry_range_high")),
                suggested_entry=_decimal_or_none(row.get("suggested_entry")),
                atr_stop=_decimal_or_none(row.get("atr_stop")),
                trend=row.get("trend"),
                rsi=_decimal_or_none(row.get("rsi")),
                gap_pct=_decimal_or_none(row.get("gap_pct")),
                accum_tag=row.get("accum_tag"),
                fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
            )
        )
        extras[ticker] = {
            "prev_high": row.get("prev_high"),
            "prev_low": row.get("prev_low"),
            "entry_range_low": row.get("entry_range_low"),
            "entry_range_high": row.get("entry_range_high"),
            "accum_tag": row.get("accum_tag"),
            "fvwap_discount_pct": row.get("fvwap_discount_pct"),
        }

    return screened_at, candidates, extras


def _display_confirmations(
    confirmations: tuple[IntradayConfirmation, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    extras: dict[str, dict] | None = None,
) -> None:
    extras = extras or {}

    typer.echo("")
    typer.echo("━" * 60)
    typer.echo(f" {confirmed_date}  INTRADAY CONFIRMATION")
    typer.echo("━" * 60)

    if not confirmations:
        typer.echo(" No candidates found in session sidecar.")
        typer.echo("━" * 60)
        return

    enters = [c for c in confirmations if c.decision.value == "ENTER"]
    waits  = [c for c in confirmations if c.decision.value == "WAIT"]
    skips  = [c for c in confirmations if c.decision.value not in ("ENTER", "WAIT")]

    # ── ENTER ──────────────────────────────────────────────────────────────
    if enters:
        typer.echo("")
        typer.echo(typer.style(" ▶ ENTER  (act now)", fg=typer.colors.GREEN, bold=True))
        for c in enters:
            ex        = extras.get(c.ticker, {})
            open_str  = f"{c.opening_price:,.0f}" if c.opening_price else "?"
            rng_low   = ex.get("entry_range_low")
            rng_high  = ex.get("entry_range_high")
            rng_str   = f"{float(rng_low):,.0f}–{float(rng_high):,.0f}" if rng_low and rng_high else "—"
            entry_str = f"{c.planned_entry:,.0f}" if c.planned_entry else "—"
            stop_str  = f"{c.stop_loss_price:,.0f}" if c.stop_loss_price else "—"
            stop_pct  = f"-{c.stop_pct:.1f}%" if c.stop_pct is not None else ""
            prev_h    = ex.get("prev_high")
            target    = f"  |  Target: Prev H {prev_h:,.0f}" if prev_h else ""

            typer.echo(
                typer.style(
                    f"   {c.ticker:<6}  open {open_str}  in range {rng_str}",
                    fg=typer.colors.GREEN,
                )
            )
            typer.echo(
                typer.style(
                    f"   → Limit BUY {entry_str}  |  Stop {stop_str} ({stop_pct}){target}",
                    fg=typer.colors.GREEN, bold=True,
                )
            )

    # ── WAIT ───────────────────────────────────────────────────────────────
    if waits:
        typer.echo("")
        typer.echo(typer.style(" ◎ WAIT  (monitor 15 min — skip if no direction)", fg=typer.colors.YELLOW, bold=True))
        for c in waits:
            ex       = extras.get(c.ticker, {})
            open_str = f"{c.opening_price:,.0f}" if c.opening_price else "?"
            rng_low  = ex.get("entry_range_low")
            rng_high = ex.get("entry_range_high")
            rng_str  = f"{float(rng_low):,.0f}–{float(rng_high):,.0f}" if rng_low and rng_high else "—"
            floor    = float(rng_low) if rng_low else None
            trigger  = f"holds above {floor:,.0f}" if floor else "shows directional move up"

            typer.echo(
                typer.style(
                    f"   {c.ticker:<6}  open {open_str}  in range {rng_str}",
                    fg=typer.colors.YELLOW,
                )
            )
            typer.echo(
                typer.style(
                    f"   → Watch volume. Enter only if price {trigger} with uptick.",
                    fg=typer.colors.YELLOW,
                )
            )

    # ── SKIP ───────────────────────────────────────────────────────────────
    if skips:
        typer.echo("")
        typer.echo(typer.style(" ✗ SKIP  (do not enter)", fg=typer.colors.BRIGHT_BLACK))
        for c in skips:
            # Last reason is the actual skip cause; first is often "open inside entry range"
            reason = c.reasons[-1] if c.reasons else c.decision.value.lower().replace("_", " ")
            typer.echo(
                typer.style(f"   {c.ticker:<6}  {reason}", fg=typer.colors.BRIGHT_BLACK)
            )

    typer.echo("")
    typer.echo("━" * 60)
    typer.echo(
        typer.style("  saham intraday log   (record this session)", fg=typer.colors.BRIGHT_BLACK)
    )
    typer.echo("━" * 60)


def _write_confirmation_sidecar(
    confirmations: tuple[IntradayConfirmation, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "confirmed_at": str(confirmed_date),
        "max_stop_pct": str(max_stop_pct),
        "confirmations": [
            {
                "ticker": c.ticker,
                "decision": c.decision.value,
                "opening_price": str(c.opening_price) if c.opening_price else None,
                "planned_entry": str(c.planned_entry) if c.planned_entry else None,
                "stop_loss_price": str(c.stop_loss_price) if c.stop_loss_price else None,
                "stop_pct": str(c.stop_pct) if c.stop_pct is not None else None,
                "reasons": list(c.reasons),
                "iev": c.iev,
                "trend": c.trend,
                "rsi": str(c.rsi) if c.rsi is not None else None,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "accum_tag": c.accum_tag,
                "fvwap_discount_pct": (
                    str(c.fvwap_discount_pct)
                    if c.fvwap_discount_pct is not None
                    else None
                ),
            }
            for c in confirmations
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def _display_intraday_review(report, journal_path: Path) -> None:
    typer.echo("")
    typer.echo("=" * 78)
    typer.echo("INTRADAY CONFIRMATION REVIEW")
    typer.echo("=" * 78)
    typer.echo(f"Journal: {journal_path}")
    typer.echo(f"Total logged entries : {report.total_entries}")
    typer.echo(f"Entries with outcome : {report.entries_with_data}")

    if report.total_entries == 0:
        typer.echo("\nNo confirmation entries logged yet.")
        typer.echo("=" * 78)
        return

    def print_bucket_table(title: str, rows) -> None:
        if not rows:
            return
        typer.echo("")
        typer.echo(title)
        typer.echo("-" * 78)
        typer.echo(
            f"{'BUCKET':<24} {'TOTAL':>6} {'DATA':>6} {'ENTER':>7} "
            f"{'UP':>5} {'STOP':>6} {'TGT1R':>6} {'AVG_R':>7}"
        )
        for row in rows:
            avg_r = f"{row.avg_close_r:+.2f}" if row.avg_close_r is not None else "-"
            typer.echo(
                f"{row.bucket:<24} {row.total:>6} {row.with_data:>6} "
                f"{row.enter_count:>7} {row.up_count:>5} "
                f"{row.stop_hit_count:>6} {row.target_1r_hit_count:>6} {avg_r:>7}"
            )

    print_bucket_table("By decision", report.decision_buckets)
    for label, rows in report.context_buckets.items():
        print_bucket_table(f"By {label}", rows)

    typer.echo("")
    typer.echo(
        "Note: manual outcomes are used first. Rows without manual outcomes use "
        "daily OHLC as a proxy; exact intraday sequence requires minute/tick data."
    )
    typer.echo("=" * 78)


@intraday_app.command("pre-open")
def pre_open(
    movers_json: Annotated[
        Optional[str],
        typer.Option("--movers-json", help='Pre-fetched movers JSON array'),
    ] = None,
    order_books_json: Annotated[
        Optional[str],
        typer.Option("--order-books-json", help='Pre-fetched order books JSON object'),
    ] = None,
    iev_min: Annotated[Optional[int], typer.Option("--iev-min", min=1)] = None,
    iep_min: Annotated[
        Optional[int],
        typer.Option("--iep-min", min=1, help="IEP floor: exclude movers with IEP below this (IDR). E.g. --iep-min 50 drops penny stocks."),
    ] = None,
    capital: Annotated[Optional[int], typer.Option("--capital", min=1)] = None,
    stop_loss: Annotated[Optional[float], typer.Option("--stop-loss")] = None,
    tick_above: Annotated[Optional[int], typer.Option("--tick-above", min=1)] = None,
    top: Annotated[
        Optional[int],
        typer.Option("--top", help="Process only top N movers by IEV (default: from YAML)"),
    ] = None,
    fast: Annotated[
        bool,
        typer.Option("--fast/--no-fast", help="Skip order book fetches (~15s total)"),
    ] = False,
    max_gap: Annotated[
        Optional[float],
        typer.Option("--max-gap", help="Override max gap % threshold (e.g. 0.04 for 4%)"),
    ] = None,
    atr_mult: Annotated[
        Optional[float],
        typer.Option("--atr-mult", help="Override ATR stop multiplier (e.g. 1.5)"),
    ] = None,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Pre-open screener config YAML path"),
    ] = None,
    legacy_strategy_path: Annotated[
        Optional[Path],
        typer.Option(
            "--strategy",
            "-s",
            help="Deprecated alias for --config",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    with_ai: Annotated[
        bool,
        typer.Option("--with-ai", help="Enable AI research (requires ANTHROPIC_API_KEY)"),
    ] = False,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Add deterministic market regime context"),
    ] = False,
    regime_universe: Annotated[
        str,
        typer.Option("--regime-universe", help="Universe for regime breadth context"),
    ] = DEFAULT_REGIME_UNIVERSE,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = DEFAULT_REGIME_BENCHMARK,
    provider: Annotated[Optional[str], typer.Option("--provider")] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless"),
    ] = True,
    allow_non_trading_day: Annotated[
        bool,
        typer.Option(
            "--allow-non-trading-day",
            help="Allow weekend/non-trading-day dry-runs that can write sidecars",
        ),
    ] = False,
    signal_strategy: Annotated[
        Optional[str],
        typer.Option(
            "--signal-strategy",
            help="Strategy name to show as extra signal column (e.g. williams-r-bounce)",
        ),
    ] = None,
) -> None:
    """
    Run the pre-open market screener for IDX stocks.

    Outputs conditional entry ranges (not fixed prices) aligned to the IDX
    call auction mechanism. Enter at open only if opening price falls within
    the displayed range.

    Examples:
        # Fast mode (no order book, ~15s):
        saham intraday pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

        # Normal mode with order book:
        saham intraday pre-open \\
          --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
          --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

        # Top 3 only, wider gap tolerance:
        saham intraday pre-open --movers-json '...' --top 3 --max-gap 0.05

        # Log results after run:
        saham intraday pre-open --movers-json '...' && saham intraday pre-open-log
    """
    resolved_config = config_path or legacy_strategy_path or DEFAULT_PRE_OPEN_CONFIG_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    overrides: dict = {
        "iev_min": iev_min,
        "iep_min": iep_min,
        "capital": capital,
        "stop_loss_pct": stop_loss,
        "tick_above": tick_above,
        "top_n": top,
        "fast_mode": fast or None,
        "max_gap": max_gap,
        "atr_mult": atr_mult,
    }
    config = _load_config(resolved_config, overrides)
    if legacy_strategy_path and not config_path:
        typer.echo(
            "Warning: --strategy is deprecated for intraday pre-open; use --config.",
            err=True,
        )
    run_guard = _build_intraday_run_guard(
        _current_idx_datetime(),
        allow_non_trading_day=allow_non_trading_day,
    )
    if run_guard.error:
        typer.echo(f"Pre-open guard: {run_guard.error}", err=True)
        raise typer.Exit(1)

    if not movers_json:
        if _playwright_available() and _session_exists():
            typer.echo("Playwright session found — running autonomously...")
            from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
            browser_provider = PlaywrightStockbitProvider(
                session_file=DEFAULT_SESSION_FILE,
                headless=headless,
            )
        else:
            if _playwright_available() and not _session_exists():
                typer.echo("Playwright installed but no session found.")
                typer.echo("Run: saham stockbit login")
            typer.echo("")
            typer.echo(f"Config: {resolved_config}")
            typer.echo(f"IEV threshold: {config.iev_min:,}")
            for warning in run_guard.warnings:
                typer.echo(f"Warning: {warning}")
            _print_browser_plan(config)
            raise typer.Exit(0)
    else:
        try:
            movers_raw = json.loads(movers_json)
            if not isinstance(movers_raw, list):
                typer.echo("Error: --movers-json must be a JSON array.", err=True)
                raise typer.Exit(1)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON in --movers-json: {e}", err=True)
            raise typer.Exit(1)

        order_books_raw: dict | None = None
        if order_books_json:
            try:
                order_books_raw = json.loads(order_books_json)
            except json.JSONDecodeError as e:
                typer.echo(f"Error: Invalid JSON in --order-books-json: {e}", err=True)
                raise typer.Exit(1)

        top_label = f"top {config.top_n}" if config.top_n else str(len(movers_raw))
        mode_label = "fast" if config.fast_mode else "normal"
        typer.echo(
            f"Running pre-open screen ({top_label} movers, IEV >= {config.iev_min:,}, "
            f"{mode_label} mode)..."
        )
        browser_provider = ManualBrowserDataProvider.from_json(movers_raw, order_books_raw)

    repository = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=repository,
    )

    ai_explainer = None
    if with_ai:
        try:
            ai_explainer = _build_ai_researcher(provider=provider)
        except Exception as e:
            typer.echo(f"Warning: Could not initialize AI research: {e}", err=True)

    use_case = PreOpenScreenUseCase(
        browser=browser_provider,
        repository=repository,
        registry=registry,
        broker_repository=broker_repo,
        ai_explainer=ai_explainer,
    )

    try:
        request = PreOpenScreenRequest(config=config, run_date=run_guard.run_at.date())
        response = use_case.execute(request)
        result = response.result

        # Optional strategy signal column
        strategy_signals: dict[str, str] = {}
        strategy_warning: str | None = None
        if signal_strategy:
            try:
                strat_loader = StrategyLoader(registry=registry)
                rules_path = strat_loader.resolve(signal_strategy)
                risk_uc = AssessRiskUseCase(repository=repository, registry=registry)
                for candidate in result.candidates:
                    try:
                        req = AssessRiskRequest(
                            ticker=candidate.ticker, rules_file=rules_path
                        )
                        res = risk_uc.execute(req)
                        strategy_signals[candidate.ticker] = res.assessment.risk_level_name
                    except Exception:
                        strategy_signals[candidate.ticker] = "?"
            except StrategyNotFoundError as e:
                strategy_warning = f"Strategy '{signal_strategy}' not found: {e}"

        data_freshness = _build_data_freshness(
            candidates=result.candidates,
            analysis_date=result.screened_date,
            market_repo=repository,
            broker_repo=broker_repo,
        )
        display_warnings = list(response.warnings) + list(run_guard.warnings)
        if strategy_warning:
            display_warnings.append(strategy_warning)
        market_regime: MarketRegimeResponse | None = None
        if with_regime:
            try:
                market_regime = _build_market_regime(
                    market_repo=repository,
                    broker_repo=broker_repo,
                    db_path=resolved_db,
                    as_of_date=result.screened_date,
                    universe=regime_universe,
                    benchmark=benchmark,
                )
            except Exception as e:
                display_warnings.append(f"Market regime unavailable: {e}")

        # Show raw IEV fetch summary so users can see what came in before filtering
        if not movers_json and getattr(response, "raw_movers", None):
            _display_raw_movers(response.raw_movers, config.top_n, config.iev_min)

        _display_results(
            candidates=result.candidates,
            screened_date=result.screened_date,
            iev_min=result.iev_min,
            total_movers_seen=result.total_movers_seen,
            warnings=display_warnings,
            data_freshness=data_freshness,
            market_regime=market_regime,
            strategy_signals=strategy_signals or None,
            strategy_name=signal_strategy,
        )

        # Write session sidecar for `saham intraday pre-open-log`
        _write_sidecar(
            result.candidates,
            result.screened_date,
            DEFAULT_SIDECAR_PATH,
            market_regime=market_regime,
        )

    except BrowserInteractionRequired as e:
        typer.echo("\nBrowser action required:", err=True)
        typer.echo(f"  URL: {e.url}", err=True)
        typer.echo(f"  {e.instructions}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Screener failed: {e}", err=True)
        raise typer.Exit(1)


@intraday_app.command("confirm-open")
def confirm_open(
    opening_json: Annotated[
        str,
        typer.Option(
            "--opening-json",
            help='Actual opening prices JSON object, e.g. {"BBCA":9050}',
        ),
    ],
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to pre-open sidecar JSON"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", help="Path to write confirmation sidecar JSON"),
    ] = None,
    max_stop: Annotated[
        float,
        typer.Option("--max-stop", help="Max stop distance as decimal, e.g. 0.07 for 7%"),
    ] = 0.07,
) -> None:
    """
    Confirm pre-open candidates after the opening auction clears.

    Reads the last `saham intraday pre-open` sidecar and actual opening prices,
    then emits deterministic ENTER / WAIT / SKIP decisions. No AI is used.

    Example:
        saham intraday confirm-open --opening-json '{"BBCA":9050,"BMRI":5875}'
    """
    sidecar_path = session or DEFAULT_SIDECAR_PATH
    output_path = output or DEFAULT_CONFIRMATION_PATH

    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar found at '{sidecar_path}'.\n"
            "Run `saham intraday pre-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        raw_opening = json.loads(opening_json)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: Invalid JSON in --opening-json: {e}", err=True)
        raise typer.Exit(1)

    if not isinstance(raw_opening, dict):
        typer.echo("Error: --opening-json must be a JSON object.", err=True)
        raise typer.Exit(1)

    try:
        opening_prices = {
            str(ticker).upper(): Decimal(str(price))
            for ticker, price in raw_opening.items()
            if price is not None
        }
    except Exception as e:
        typer.echo(f"Error: opening prices must be numeric: {e}", err=True)
        raise typer.Exit(1)

    if max_stop <= 0:
        typer.echo("Error: --max-stop must be positive.", err=True)
        raise typer.Exit(1)

    screened_at, candidates, extras = _load_confirmation_candidates(sidecar_path, opening_prices)
    use_case = ConfirmIntradayOpenUseCase()
    result = use_case.execute(
        ConfirmIntradayOpenRequest(
            candidates=candidates,
            run_date=screened_at,
            max_stop_pct=Decimal(str(max_stop)),
        )
    )

    _display_confirmations(
        result.confirmations,
        result.confirmed_date,
        result.max_stop_pct,
        extras=extras,
    )
    _write_confirmation_sidecar(
        result.confirmations,
        result.confirmed_date,
        result.max_stop_pct,
        output_path,
    )


@intraday_app.command("confirm-log")
@intraday_app.command("log")
def confirm_log(
    confirmation: Annotated[
        Optional[Path],
        typer.Option(
            "--confirmation",
            help="Path to confirmation sidecar JSON",
        ),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
) -> None:
    """
    Append the latest `confirm-open` result to the intraday confirmation journal.

    The journal is idempotent by (confirmed_at, ticker), so repeated logs for the
    same confirmation run do not duplicate rows.
    """
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )

    confirmation_path = confirmation or DEFAULT_CONFIRMATION_PATH
    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH

    if not confirmation_path.exists():
        typer.echo(
            f"No confirmation sidecar found at '{confirmation_path}'.\n"
            "Run `saham intraday confirm-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    with open(confirmation_path) as f:
        data = json.load(f)

    confirmed_at = date.fromisoformat(data["confirmed_at"])
    entries = [
        IntradayConfirmationJournalEntry(
            confirmed_at=confirmed_at,
            ticker=row["ticker"],
            decision=row["decision"],
            reason_codes=tuple(row.get("reasons", [])),
            opening_price=_decimal_or_none(row.get("opening_price")),
            planned_entry=_decimal_or_none(row.get("planned_entry")),
            stop_loss_price=_decimal_or_none(row.get("stop_loss_price")),
            stop_pct=_decimal_or_none(row.get("stop_pct")),
            iev=row.get("iev"),
            trend=row.get("trend"),
            rsi=_decimal_or_none(row.get("rsi")),
            gap_pct=_decimal_or_none(row.get("gap_pct")),
            accum_tag=row.get("accum_tag"),
            fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
        )
        for row in data.get("confirmations", [])
    ]

    store = IntradayConfirmationCsvStore(journal_path)
    count = store.append(entries)
    if count == 0:
        typer.echo(
            f"Already logged for {confirmed_at} — no new rows added ({journal_path})"
        )
    else:
        typer.echo(f"Logged {count} confirmation(s) for {confirmed_at} → {journal_path}")


@intraday_app.command("confirm-review")
@intraday_app.command("review")
def confirm_review(
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Review logged intraday confirmation decisions by decision and context buckets.

    Uses local daily candles as an outcome proxy. Exact intraday stop/target
    sequencing requires finer-grained data and is intentionally out of scope here.
    """
    from src.application.services.intraday_confirmation_journal import (
        IntradayConfirmationJournalService,
    )
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )

    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal found at '{journal_path}'.\n"
            "Run `saham intraday confirm-log` after confirming opens first.",
            err=True,
        )
        raise typer.Exit(1)

    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = IntradayConfirmationJournalService(store=store, repository=repository)
    report = service.review()
    _display_intraday_review(report, journal_path)


@intraday_app.command("confirm-outcome")
@intraday_app.command("outcome")
def confirm_outcome(
    ticker: Annotated[str, typer.Argument(help="Ticker to update (e.g. BBCA)")],
    entry: Annotated[
        float,
        typer.Option("--entry", help="Actual executed entry price", min=0.0001),
    ],
    exit_price: Annotated[
        float,
        typer.Option("--exit", help="Actual executed exit price", min=0.0001),
    ],
    result: Annotated[
        str,
        typer.Option("--result", help="Outcome label: target, stop, manual, breakeven"),
    ] = "manual",
    confirmed_date: Annotated[
        Optional[str],
        typer.Option("--date", help="Confirmation date YYYY-MM-DD (default: today)"),
    ] = None,
    notes: Annotated[
        Optional[str],
        typer.Option("--notes", help="Optional execution notes"),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Record actual trade outcome for a logged intraday confirmation.

    This upgrades `confirm-review` from daily OHLC proxy to actual execution data
    for that ticker/date.
    """
    from src.application.services.intraday_confirmation_journal import (
        IntradayConfirmationJournalService,
    )
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )

    valid_results = {"target", "stop", "manual", "breakeven"}
    outcome_result = result.lower()
    if outcome_result not in valid_results:
        typer.echo(
            f"Error: --result must be one of: {', '.join(sorted(valid_results))}",
            err=True,
        )
        raise typer.Exit(1)

    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH
    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal found at '{journal_path}'.\n"
            "Run `saham intraday confirm-log` first.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        target_date = (
            date.fromisoformat(confirmed_date) if confirmed_date else date.today()
        )
    except ValueError:
        typer.echo("Error: --date must use YYYY-MM-DD format.", err=True)
        raise typer.Exit(1)

    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = IntradayConfirmationJournalService(store=store, repository=repository)
    updated, outcome_r = service.record_outcome(
        confirmed_at=target_date,
        ticker=ticker.upper(),
        actual_entry_price=Decimal(str(entry)),
        actual_exit_price=Decimal(str(exit_price)),
        outcome_result=outcome_result,
        notes=notes,
    )

    if not updated:
        typer.echo(
            f"No logged confirmation found for {ticker.upper()} on {target_date}.",
            err=True,
        )
        raise typer.Exit(1)

    r_label = f"{outcome_r:+.2f}R" if outcome_r is not None else "N/A"
    typer.echo(
        f"Recorded outcome for {ticker.upper()} on {target_date}: "
        f"{outcome_result} | entry={entry:,.0f} exit={exit_price:,.0f} | R={r_label}"
    )


@intraday_app.command("pre-open-log")
def log_session(
    session: Annotated[
        Optional[Path],
        typer.Option(
            "--session",
            help="Path to session sidecar JSON (default: journals/.last-session.json)",
        ),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Path to journal CSV (default: journals/pre-open.csv)"),
    ] = None,
) -> None:
    """
    Append last screener run to the paper trade journal.

    Reads the session sidecar written by `saham intraday pre-open` and
    appends one row per candidate to the journal CSV. Idempotent:
    re-running for the same date never duplicates rows.

    Example:
        saham intraday pre-open --movers-json '...'
        saham intraday pre-open-log
        saham intraday pre-open-review --horizon 5
    """
    from src.application.services.paper_trade_journal import PaperTradeJournalService
    from src.domain.value_objects.screener_result import ScreenerCandidate
    from src.infrastructure.persistence.journal_csv_writer import JournalCsvWriter

    sidecar_path = session or DEFAULT_SIDECAR_PATH
    journal_path = journal or DEFAULT_JOURNAL_PATH

    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar found at '{sidecar_path}'.\n"
            "Run `saham intraday pre-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    with open(sidecar_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])

    # Reconstruct minimal ScreenerCandidate objects for the journal service
    candidates = []
    for row in data["candidates"]:
        candidates.append(
            ScreenerCandidate(
                ticker=row["ticker"],
                iev=row["iev"],
                entry_price=Decimal(row["suggested_entry"]) if row.get("suggested_entry") else None,
                stop_loss_price=Decimal(row["atr_stop"]) if row.get("atr_stop") else None,
                capital=Decimal("0"),
                trend_signal=row.get("trend"),
                rsi=Decimal(row["rsi"]) if row.get("rsi") else None,
                gap_pct=Decimal(row["gap_pct"]) if row.get("gap_pct") else None,
                entry_range_low=(
                    Decimal(row["entry_range_low"]) if row.get("entry_range_low") else None
                ),
                entry_range_high=(
                    Decimal(row["entry_range_high"]) if row.get("entry_range_high") else None
                ),
            )
        )

    store = JournalCsvWriter(journal_path)
    repository = SQLiteMarketRepository(db_path=DEFAULT_DB_PATH)
    service = PaperTradeJournalService(store=store, repository=repository)

    count = service.log_session(candidates, screened_at)
    if count == 0:
        typer.echo(f"Already logged for {screened_at} — no new rows added ({journal_path})")
    else:
        typer.echo(f"Logged {count} candidate(s) for {screened_at} → {journal_path}")


@intraday_app.command("pre-open-review")
def review(
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Path to journal CSV"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    horizon: Annotated[
        int,
        typer.Option(
            "--horizon",
            help="Trading days after screen date to check close price",
            min=1,
        ),
    ] = 5,
) -> None:
    """
    Review paper trade journal: hit-rate and direction accuracy.

    Fetches actual opening prices and N-day closes from the local database
    and computes what % of entry ranges were accurate.

    Example:
        saham intraday pre-open-review --horizon 5
    """
    from src.application.services.paper_trade_journal import PaperTradeJournalService
    from src.infrastructure.persistence.journal_csv_writer import JournalCsvWriter

    journal_path = journal or DEFAULT_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham intraday pre-open-log` after a screening session first.",
            err=True,
        )
        raise typer.Exit(1)

    store = JournalCsvWriter(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = PaperTradeJournalService(store=store, repository=repository)

    report = service.review(horizon_days=horizon)

    typer.echo("")
    typer.echo("=" * 55)
    typer.echo("PAPER TRADE JOURNAL REVIEW")
    typer.echo("=" * 55)
    typer.echo(f"Journal: {journal_path}")
    typer.echo(f"Total logged entries : {report.total_entries}")
    typer.echo(f"Entries with DB data : {report.entries_with_data}")

    if report.hit_rate_pct is not None:
        typer.echo(f"\nEntry range hit rate : {report.hit_rate_pct:.1f}%")
        typer.echo("  (% of sessions where opening price fell within entry range)")
    else:
        typer.echo("\nEntry range hit rate : N/A (no actual open prices yet)")

    if report.direction_accuracy_1d is not None:
        typer.echo(f"Direction accuracy 1d: {report.direction_accuracy_1d:.1f}%")
        typer.echo(f"Direction accuracy {horizon}d: {report.direction_accuracy_5d:.1f}%"
                   if report.direction_accuracy_5d else "")
    else:
        typer.echo("Direction accuracy   : N/A (need BULLISH calls + 1d close data)")

    if report.per_trend_breakdown:
        typer.echo("\nPer-trend breakdown:")
        typer.echo(f"  {'TREND':<10} {'TOTAL':>6} {'IN_RANGE':>9} {'UP_1D':>7}")
        typer.echo("  " + "-" * 35)
        for trend, stats in report.per_trend_breakdown.items():
            typer.echo(
                f"  {trend:<10} {stats['total']:>6} {stats['in_range']:>9} {stats['up_1d']:>7}"
            )

    typer.echo("")
    typer.echo("Note: hit-rate measures ENTRY RANGE accuracy, not trade profitability.")
    typer.echo("After 20+ sessions this becomes statistically meaningful.")
    typer.echo("=" * 55)


def _build_ai_researcher(provider: Optional[str] = None):
    from src.application.services.ai_research import ClaudeTickerResearcher
    if provider and provider not in ("claude", None):
        typer.echo(
            "Warning: AI research only supports 'claude' provider. Falling back.",
            err=True,
        )
    return ClaudeTickerResearcher()


def _display_intraday_backtest(response: IntradayBacktestResponse, show_trades: int) -> None:
    """Print walk-forward intraday backtest results to the console."""
    W = 72
    typer.echo("")
    typer.echo(typer.style("=" * W, fg=typer.colors.CYAN))
    typer.echo(typer.style("INTRADAY WALK-FORWARD BACKTEST (Option A — daily OHLC proxy)", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * W, fg=typer.colors.CYAN))
    typer.echo(f"Period : {response.start_date} to {response.end_date}")
    typer.echo(
        f"Config : cost={float(response.cost_bps):g} bps/side | "
        f"max_daily={response.max_daily_positions} | "
        f"include_wait={response.include_wait}"
    )
    typer.echo(
        "Entry  : candle.open (IDX 09:00 call-auction clearing price)\n"
        "Exit   : H/L/close same day. Both-breached → stop (conservative).\n"
        "IEV    : not replayed — all universe tickers screened each day."
    )
    typer.echo("")

    # ── Equity & trade stats ──────────────────────────────────────────────────
    typer.echo(f"{'METRIC':<30} {'VALUE':>20}")
    typer.echo("-" * 54)
    typer.echo(f"{'Initial capital':<30} {float(response.initial_capital):>20,.0f}")
    typer.echo(f"{'Final equity':<30} {float(response.final_equity):>20,.0f}")
    typer.echo(f"{'Total return':<30} {_fmt_pct(response.total_return_pct, True):>20}")
    typer.echo(f"{'Max drawdown':<30} {_fmt_pct(response.max_drawdown_pct, True):>20}")
    typer.echo(f"{'Trades':<30} {response.trade_count:>20}")
    typer.echo(f"{'Win rate':<30} {_fmt_pct(response.win_rate_pct):>20}")
    typer.echo(f"{'Avg trade return (net)':<30} {_fmt_pct(response.avg_trade_return_pct, True):>20}")
    typer.echo(f"{'Avg winner':<30} {_fmt_pct(response.avg_winner_pct, True):>20}")
    typer.echo(f"{'Avg loser':<30} {_fmt_pct(response.avg_loser_pct, True):>20}")
    pf_str = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    typer.echo(f"{'Profit factor':<30} {pf_str:>20}")
    exp_str = _fmt_pct(response.expectancy_pct, signed=True) if response.expectancy_pct is not None else "N/A"
    typer.echo(f"{'Expectancy':<30} {exp_str:>20}")
    r_str = f"{response.avg_r_multiple:.3f}R" if response.avg_r_multiple is not None else "N/A"
    typer.echo(f"{'Avg R-multiple':<30} {r_str:>20}")
    typer.echo(f"{'Trading days':<30} {response.trading_days:>20}")
    typer.echo(f"{'Days with trades':<30} {response.days_with_trades:>20}")
    typer.echo("")

    # ── Exit reasons ──────────────────────────────────────────────────────────
    if response.exit_reason_counts:
        typer.echo("EXIT REASONS")
        total_trades = response.trade_count
        for reason, count in sorted(response.exit_reason_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100 if total_trades else 0
            flag = ""
            if reason == "both_assume_stop" and total_trades > 0 and count / total_trades > 0.15:
                flag = " ← H/L ambiguity HIGH (>15%)"
            typer.echo(f"  {reason:<22} {count:>5}  ({pct:.0f}%){flag}")
        typer.echo("")

    # ── Signal-quality breakdowns ─────────────────────────────────────────────
    def _print_breakdown(title: str, rows: list[dict]) -> None:
        if not rows:
            return
        typer.echo(title)
        typer.echo(f"  {'LABEL':<22} {'TRADES':>7} {'WIN%':>7} {'AVG_RET':>9} {'TOTAL_PNL':>14}")
        typer.echo("  " + "-" * 63)
        for row in rows:
            pnl = float(row["total_pnl"])
            pnl_str = f"{pnl:+,.0f}"
            wr = _fmt_pct(row["win_rate_pct"])
            ar = _fmt_pct(row["avg_return_pct"], signed=True)
            typer.echo(f"  {row['label']:<22} {row['count']:>7} {wr:>7} {ar:>9} {pnl_str:>14}")
        typer.echo("")

    _print_breakdown("BY ACCUM TAG", response.by_accum_tag)
    _print_breakdown("BY FVWAP SIGN", response.by_fvwap_sign)
    _print_breakdown("BY RSI BUCKET", response.by_rsi_bucket)
    _print_breakdown("TOP TICKERS (by trade count)", response.by_ticker)

    # ── Recent trades ─────────────────────────────────────────────────────────
    if show_trades > 0 and response.trades:
        display = response.trades[-show_trades:]
        typer.echo(f"RECENT {len(display)} TRADES (of {response.trade_count} total)")
        typer.echo(
            f"  {'DATE':<12} {'TICKER':<6} {'DEC':<6} {'OPEN':>7} "
            f"{'STOP':>7} {'TARGET':>7} {'EXIT':>7} {'REASON':<18} {'RET%':>7} {'PNL':>10}"
        )
        typer.echo("  " + "-" * 100)
        for t in display:
            pnl_col = f"{float(t.pnl):+,.0f}"
            ret_col = _fmt_pct(t.net_return_pct, signed=True)
            typer.echo(
                f"  {t.trade_date.isoformat():<12} {t.ticker:<6} {t.decision:<6} "
                f"{float(t.entry_price):>7,.0f} {float(t.stop_price):>7,.0f} "
                f"{float(t.target_price):>7,.0f} {float(t.exit_price):>7,.0f} "
                f"{t.exit_reason:<18} {ret_col:>7} {pnl_col:>10}"
            )
        typer.echo("")

    # ── Warnings ──────────────────────────────────────────────────────────────
    for warning in response.warnings:
        prefix = "  ⚠ " if "WARNING" in warning else "  ! "
        typer.echo(typer.style(prefix + warning, fg=typer.colors.YELLOW))
    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * W, fg=typer.colors.CYAN))


@intraday_app.command("backtest")
def intraday_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI BMRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = 100_000_000,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade", min=0.01),
    ] = 1.0,
    max_daily_positions: Annotated[
        int,
        typer.Option("--max-daily-positions", help="Max simultaneous trades per day", min=1),
    ] = 3,
    max_stop: Annotated[
        float,
        typer.Option("--max-stop", help="Max allowed stop distance (e.g. 0.07 = 7%)", min=0.005),
    ] = 0.07,
    cost_bps: Annotated[
        float,
        typer.Option("--cost-bps", help="Transaction cost in basis points per side", min=0),
    ] = 20.0,
    include_wait: Annotated[
        bool,
        typer.Option("--include-wait/--no-include-wait", help="Treat WAIT decisions as ENTER"),
    ] = False,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance", min=0.1),
    ] = 1.0,
    rsi_overbought: Annotated[
        float,
        typer.Option("--rsi-overbought", help="RSI threshold for BEARISH classification"),
    ] = 75.0,
    iev_top_n: Annotated[
        int,
        typer.Option("--iev-top-n", help="When IEV snapshots are available, only trade top-N movers", min=1),
    ] = 5,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to display", min=0),
    ] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Walk-forward backtest of the intraday pre-open workflow (Option A: daily OHLC proxy).

    When IEV snapshot data is available (collected via 'saham intraday collect-iev'),
    only the top --iev-top-n movers per day are traded — matching the live workflow.
    On days without a snapshot, the full universe is screened (with a warning).
    Entries/exits use candle.open/high/low/close. All trades exit same day.

    Examples:

      saham intraday backtest --universe lq45 --start 2025-12-01

      saham intraday backtest BBCA BBRI BMRI ASII TLKM --start 2025-09-01

      saham intraday backtest --universe lq45 --start 2025-12-01 --include-wait

      saham intraday backtest --universe idx80 --start 2025-09-01 --format json
    """
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as exc:
        typer.echo(f"Error: invalid date format — {exc}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(
        f"Intraday backtest: {len(ticker_list)} tickers | "
        f"{start_date} to {end_date} | "
        f"max_daily={max_daily_positions} | "
        f"include_wait={include_wait}",
        err=True,
    )

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry()

    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
    iev_repo = SQLiteIEVRepository(resolved_db)
    coverage = iev_repo.get_coverage()
    if coverage["total_dates"] > 0:
        typer.echo(
            f"IEV snapshots: {coverage['total_dates']} days "
            f"({coverage['first_date']} → {coverage['last_date']}) — "
            f"top-{iev_top_n} filter will be applied where available.",
            err=True,
        )
    else:
        typer.echo(
            "No IEV snapshots found. Screening full universe each day. "
            "Run 'saham intraday collect-iev' at 08:50 WIB to start collecting.",
            err=True,
        )
        iev_repo = None

    use_case = IntradayBacktestUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        indicator_registry=registry,
        iev_repository=iev_repo,
    )

    try:
        response = use_case.execute(IntradayBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_daily_positions=max_daily_positions,
            max_stop_pct=Decimal(str(max_stop)),
            cost_bps=Decimal(str(cost_bps)),
            include_wait=include_wait,
            atr_multiplier=Decimal(str(atr_mult)),
            rsi_overbought_threshold=Decimal(str(rsi_overbought)),
            iev_top_n=iev_top_n,
        ))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        import json as _json
        typer.echo(_json.dumps(
            {
                "start_date": response.start_date.isoformat(),
                "end_date": response.end_date.isoformat(),
                "initial_capital": str(response.initial_capital),
                "cost_bps": str(response.cost_bps),
                "include_wait": response.include_wait,
                "final_equity": str(response.final_equity),
                "total_return_pct": response.total_return_pct,
                "max_drawdown_pct": response.max_drawdown_pct,
                "trade_count": response.trade_count,
                "win_rate_pct": response.win_rate_pct,
                "avg_trade_return_pct": response.avg_trade_return_pct,
                "profit_factor": response.profit_factor,
                "expectancy_pct": response.expectancy_pct,
                "avg_r_multiple": response.avg_r_multiple,
                "exit_reason_counts": response.exit_reason_counts,
                "decisions": response.decisions,
                "by_accum_tag": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_accum_tag
                ],
                "by_fvwap_sign": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_fvwap_sign
                ],
                "by_rsi_bucket": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_rsi_bucket
                ],
                "by_ticker": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_ticker
                ],
                "trades": [t.to_dict() for t in response.trades],
                "warnings": response.warnings,
            },
            indent=2,
            default=str,
        ))
        return

    _display_intraday_backtest(response, show_trades=show_trades)


@intraday_app.command("collect-iev")
def collect_iev(
    top_n: Annotated[
        int,
        typer.Option("--top-n", help="Max movers to capture (default 50)", min=5),
    ] = 50,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
    no_headless: Annotated[
        bool,
        typer.Option("--no-headless", help="Show browser window"),
    ] = False,
) -> None:
    """
    Capture today's IEV mover ranking from Stockbit and store it locally.

    Run this at 08:50 WIB each trading day (during the pre-open auction window)
    to build a historical IEV dataset for backtesting. After a few months of
    daily collection the intraday backtest can filter candidates by IEV rank,
    matching live workflow behaviour.

    Requires an active Stockbit session (saham stockbit login).

    Examples:

      saham intraday collect-iev

      saham intraday collect-iev --top-n 30
    """
    from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    resolved_db = db_path or DEFAULT_DB_PATH

    now_idx = _current_idx_datetime()
    today = now_idx.date()
    is_ncp = now_idx.time() >= time(8, 56)

    try:
        provider = PlaywrightStockbitProvider(headless=not no_headless)
    except Exception as exc:
        typer.echo(f"Error initialising Stockbit provider: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Fetching IEV snapshot (top {top_n} movers)...", err=True)
    try:
        movers = provider.fetch_iev_snapshot(top_n=top_n)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if not movers:
        typer.echo("No movers returned — session may be expired. Run: saham stockbit login", err=True)
        raise typer.Exit(1)

    repo = SQLiteIEVRepository(resolved_db)
    # Strip tz for naive storage; repo computes is_ncp_locked from the time component.
    written = repo.save_snapshot(today, movers, collected_at=now_idx.replace(tzinfo=None))
    deltas = repo.get_iev_delta(today)

    iep_captured = sum(1 for m in movers if m.iep is not None)
    ncp_badge = "[NCP LOCKED]" if is_ncp else "[PRE-NCP]"
    typer.echo(
        f"Saved {written} movers for {today.isoformat()} to {resolved_db} "
        f"(IEP captured: {iep_captured}/{written})"
    )
    typer.echo(f"  Captured at {now_idx.strftime('%H:%M:%S')} WIB  {ncp_badge}")
    typer.echo("")

    show_delta = bool(deltas)
    header = f"  {'RANK':>4}  {'TICKER':<8}  {'IEV':>12}  {'IEP':>8}"
    sep    = f"  {'-'*4}  {'-'*8}  {'-'*12}  {'-'*8}"
    if show_delta:
        header += f"  {'ΔIEV':>10}"
        sep    += f"  {'-'*10}"
    typer.echo(header)
    typer.echo(sep)
    for i, m in enumerate(movers[:20], 1):
        iep_str = f"{m.iep:,}" if m.iep is not None else "—"
        row = f"  {i:>4}  {m.ticker:<8}  {m.iev:>12,}  {iep_str:>8}"
        if show_delta:
            d = deltas.get(m.ticker.upper())
            delta_str = f"{'+' if d and d > 0 else ''}{d:,}" if d is not None else "—"
            row += f"  {delta_str:>10}"
        typer.echo(row)
    if len(movers) > 20:
        typer.echo(f"  ... and {len(movers) - 20} more stored in database")

    # Informational penny-stock count (IEP floor not enforced here — that is pre-open's job)
    iep_floor = 50
    passes_floor = sum(1 for m in movers if m.iep is not None and m.iep >= iep_floor)
    typer.echo(f"\n  Movers with IEP >= {iep_floor}: {passes_floor}/{len(movers)}")

    coverage = repo.get_coverage()
    typer.echo("")
    typer.echo(
        f"IEV/IEP history: {coverage['total_dates']} days "
        f"({coverage['first_date']} → {coverage['last_date']}), "
        f"avg {coverage['avg_movers_per_day']:.0f} movers/day, "
        f"IEP fill {coverage['iep_fill_pct']:.0f}%"
    )


@intraday_app.command("save-session")
def save_session() -> None:
    """
    Deprecated. Use: saham stockbit login
    """
    typer.echo(
        "This command has moved. Use:\n\n"
        "  saham stockbit login\n\n"
        "Run 'saham stockbit --help' for all Stockbit session commands.",
        err=True,
    )
    raise typer.Exit(1)
