"""
CLI commands for the intraday trading command family.

Usage patterns:

  # Autonomous (playwright + saved session):
  saham screen pre-open

  # Fast mode (no order book, ~15s):
  saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

  # Normal mode with order book data:
  saham screen pre-open \\
    --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
    --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

  # Paper trade journal:
  saham trade confirm
  saham trade log intraday

Layer: Adapter
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Optional

if TYPE_CHECKING:
    from src.domain.value_objects.market_status import MarketStatus
from zoneinfo import ZoneInfo

import typer
import yaml

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.confirm_intraday_open import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.application.use_case.intraday_backtest import (
    IntradayBacktestRequest,
    IntradayBacktestResponse,
    IntradayBacktestUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeResponse,
)
from src.application.use_case.pre_open_screen import (
    PreOpenScreenConfig,
    PreOpenScreenUseCase,
)
from src.application.use_case.pre_open_workflow import (
    PreOpenDataFreshness,
    PreOpenWorkflowRequest,
    PreOpenWorkflowUseCase,
)
from src.application.use_case.resolve_opening_prices import (
    OpeningPriceObservation,
    ResolveOpeningPricesRequest,
    ResolveOpeningPricesUseCase,
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

from src.infrastructure.config.app_config import APP_CFG

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_PRE_OPEN_CONFIG_PATH = Path("config/pre_open_screener.yaml")
DEFAULT_SESSION_FILE = Path("stockbit_session.json")
DEFAULT_SIDECAR_PATH = Path("journals/.last-session.json")
DEFAULT_CONFIRMATION_PATH = Path("journals/.last-confirmation.json")
DEFAULT_CONFIRMATION_JOURNAL_PATH = Path("journals/intraday-confirmations.csv")
DEFAULT_REGIME_UNIVERSE = APP_CFG.analysis.regime_universe
DEFAULT_REGIME_BENCHMARK = APP_CFG.analysis.benchmark
IDX_TIMEZONE = ZoneInfo("Asia/Jakarta")
PRE_OPEN_START = time(8, 45)
PRE_OPEN_END = time(9, 0)


@dataclass(frozen=True)
class IntradayRunGuard:
    """Runtime guard for pre-open workflow timing."""

    run_at: datetime
    warnings: tuple[str, ...] = ()
    error: str | None = None


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


def _get_market_status() -> "MarketStatus":
    """Return current IDX market status from Stockbit if session available,
    else from local wall-clock. Never raises."""
    from src.infrastructure.browser.stockbit_market_time import get_current_market_status
    return get_current_market_status()  # reads cache first, then tries Stockbit (token already held in-process)


def _build_intraday_run_guard(
    run_at: datetime,
    allow_non_trading_day: bool = False,
    market_status: "MarketStatus | None" = None,
) -> IntradayRunGuard:
    """Build deterministic timing warnings/errors for the pre-open workflow.

    When market_status comes from Stockbit (source='stockbit'), the weekend
    check is replaced by the API's is_open / session_name — this correctly
    handles IDX public holidays that fall on weekdays.
    """
    warnings: list[str] = []
    local_run_at = run_at.astimezone(IDX_TIMEZONE)

    # Non-trading day check
    status = market_status or _get_market_status()
    if status.source == "stockbit":
        # Canonical: trust the API — closed AND not pre-open = non-trading day
        if not status.is_open and not status.is_pre_open:
            message = (
                f"{local_run_at.date()} is a non-trading day "
                f"({status.session_name} per Stockbit). "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return IntradayRunGuard(run_at=local_run_at, error=message)
            warnings.append(message)
    else:
        # Fallback: wall-clock weekend check
        if local_run_at.weekday() >= 5:
            message = (
                f"{local_run_at.date()} is a weekend in Asia/Jakarta. "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return IntradayRunGuard(run_at=local_run_at, error=message)
            warnings.append(message)

    # Pre-open window timing warning
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

def _display_data_freshness(freshness: PreOpenDataFreshness | None) -> None:
    from src.adapters.cli.intraday_pre_open_display import display_data_freshness
    display_data_freshness(freshness)


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    from src.adapters.cli.intraday_pre_open_display import fmt_pct
    return fmt_pct(value, signed)


def _format_market_regime(response: MarketRegimeResponse) -> str:
    from src.adapters.cli.intraday_pre_open_display import format_market_regime
    return format_market_regime(response)


def _market_regime_warning(response: MarketRegimeResponse) -> str | None:
    from src.adapters.cli.intraday_pre_open_display import market_regime_warning
    return market_regime_warning(response)


def _display_market_regime(response: MarketRegimeResponse | None) -> None:
    from src.adapters.cli.intraday_pre_open_display import display_market_regime
    display_market_regime(response)


def _display_raw_movers(raw_movers: list, top_n: int | None, iev_min: int) -> None:
    from src.adapters.cli.intraday_pre_open_display import display_raw_movers
    display_raw_movers(raw_movers=raw_movers, top_n=top_n, iev_min=iev_min)


def _verdict(c: "ScreenerCandidate") -> str:
    from src.adapters.cli.intraday_pre_open_display import verdict
    return verdict(c)


def _signal_col(c: "ScreenerCandidate") -> str:
    from src.adapters.cli.intraday_pre_open_display import signal_col
    return signal_col(c)


def _print_browser_plan(config: PreOpenScreenConfig) -> None:
    from src.adapters.cli.intraday_pre_open_display import print_browser_plan
    print_browser_plan(config)


def _display_pre_open_summary_panel(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: PreOpenDataFreshness | None,
    market_regime: MarketRegimeResponse | None,
) -> None:
    from src.adapters.cli.intraday_pre_open_display import display_pre_open_summary_panel
    display_pre_open_summary_panel(
        candidates=candidates,
        screened_date=screened_date,
        iev_min=iev_min,
        total_movers_seen=total_movers_seen,
        warnings=warnings,
        data_freshness=data_freshness,
        market_regime=market_regime,
    )


def _notation_label(snapshot) -> str:
    from src.adapters.cli.intraday_pre_open_display import notation_label
    return notation_label(snapshot)


def _display_results(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    iev_min: int,
    total_movers_seen: int,
    warnings: list[str],
    data_freshness: PreOpenDataFreshness | None = None,
    market_regime: MarketRegimeResponse | None = None,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    from src.adapters.cli.intraday_pre_open_display import display_results
    display_results(
        candidates=candidates,
        screened_date=screened_date,
        iev_min=iev_min,
        total_movers_seen=total_movers_seen,
        warnings=warnings,
        data_freshness=data_freshness,
        market_regime=market_regime,
        strategy_signals=strategy_signals,
        strategy_name=strategy_name,
    )


def _write_sidecar(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    sidecar_path: Path,
    market_regime: MarketRegimeResponse | None = None,
) -> None:
    """Write session sidecar JSON so `saham trade confirm` can read it."""
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
                "ticker_notation": c.ticker_notation.to_dict() if c.ticker_notation else None,
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
    observations: dict[str, OpeningPriceObservation] | None = None,
) -> tuple[date, list[IntradayConfirmationCandidate], dict[str, dict]]:
    with open(session_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])
    candidates: list[IntradayConfirmationCandidate] = []
    extras: dict[str, dict] = {}  # {ticker: {prev_high, prev_low, entry_range_low}}
    observations = observations or {}

    for row in data.get("candidates", []):
        ticker = str(row["ticker"]).upper()
        observation = observations.get(ticker)
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
                opening_price_source=observation.source if observation else None,
                opening_price_confidence=observation.confidence if observation else None,
                opening_price_timestamp=(
                    observation.timestamp.isoformat()
                    if observation and observation.timestamp
                    else None
                ),
                auto_confirmed=observation.auto_confirmed if observation else False,
                manual_override=observation.manual_override if observation else False,
            )
        )
        extras[ticker] = {
            "prev_high": row.get("prev_high"),
            "prev_low": row.get("prev_low"),
            "entry_range_low": row.get("entry_range_low"),
            "entry_range_high": row.get("entry_range_high"),
            "accum_tag": row.get("accum_tag"),
            "fvwap_discount_pct": row.get("fvwap_discount_pct"),
            "opening_price_source": observation.source if observation else None,
            "opening_price_confidence": observation.confidence if observation else None,
            "opening_price_reason": observation.reason if observation else None,
            "auto_confirmed": observation.auto_confirmed if observation else False,
            "manual_override": observation.manual_override if observation else False,
        }

    return screened_at, candidates, extras


def _load_confirmation_tickers(session_path: Path) -> tuple[date, list[str]]:
    with open(session_path) as f:
        data = json.load(f)
    screened_at = date.fromisoformat(data["screened_at"])
    tickers = [str(row["ticker"]).upper() for row in data.get("candidates", [])]
    return screened_at, tickers


def _format_ticker_preview(tickers: list[str], *, limit: int = 8) -> str:
    from src.adapters.cli.intraday_confirmation_display import format_ticker_preview
    return format_ticker_preview(tickers, limit=limit)


def _fmt_price(value: Decimal | None) -> str:
    from src.adapters.cli.intraday_confirmation_display import fmt_price
    return fmt_price(value)


def _fmt_signed_decimal(value: Decimal | None, suffix: str = "") -> str:
    from src.adapters.cli.intraday_confirmation_display import fmt_signed_decimal
    return fmt_signed_decimal(value, suffix)


def _format_opening_observation_status(
    index: int,
    total: int,
    observation: OpeningPriceObservation,
) -> str:
    from src.adapters.cli.intraday_confirmation_display import format_opening_observation_status
    return format_opening_observation_status(index, total, observation)


def _display_confirmations(
    confirmations: tuple[IntradayConfirmation, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    extras: dict[str, dict] | None = None,
) -> None:
    from src.adapters.cli.intraday_confirmation_display import display_confirmations
    display_confirmations(
        confirmations=confirmations,
        confirmed_date=confirmed_date,
        max_stop_pct=max_stop_pct,
        extras=extras,
    )


def _display_intraday_review(report, journal_path: Path) -> None:
    from src.adapters.cli.intraday_confirmation_display import display_intraday_review
    display_intraday_review(report=report, journal_path=journal_path)


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
                "opening_price_source": c.opening_price_source,
                "opening_price_confidence": c.opening_price_confidence,
                "opening_price_timestamp": c.opening_price_timestamp,
                "auto_confirmed": c.auto_confirmed,
                "manual_override": c.manual_override,
            }
            for c in confirmations
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


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
        saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

        # Normal mode with order book:
        saham screen pre-open \\
          --movers-json '[{"ticker":"BBCA","iev":150000}]' \\
          --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

        # Top 3 only, wider gap tolerance:
        saham screen pre-open --movers-json '...' --top 3 --max-gap 0.05

        # Confirm and log results after run:
        saham screen pre-open --movers-json '...'
        saham trade confirm --opening-json '{"BBCA":9050}'
        saham trade log intraday
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
                typer.echo("Run: saham fetch stockbit login")
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

    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider

    notation_provider = StockbitTickerNotationProvider(broker_provider=None, db_path=resolved_db)

    use_case = PreOpenScreenUseCase(
        browser=browser_provider,
        repository=repository,
        registry=registry,
        broker_repository=broker_repo,
        ai_explainer=ai_explainer,
        ticker_notation_provider=notation_provider,
    )
    workflow = PreOpenWorkflowUseCase(
        screen_use_case=use_case,
        market_repository=repository,
        broker_repository=broker_repo,
        registry=registry,
    )

    try:
        response = workflow.execute(
            PreOpenWorkflowRequest(
                config=config,
                run_date=run_guard.run_at.date(),
                guard_warnings=run_guard.warnings,
                with_regime=with_regime,
                regime_universe=regime_universe,
                benchmark=benchmark,
                db_path=resolved_db,
                signal_strategy=signal_strategy,
            )
        )
        result = response.result

        # Show raw IEV fetch summary so users can see what came in before filtering
        if not movers_json and getattr(response, "raw_movers", None):
            _display_raw_movers(response.raw_movers, config.top_n, config.iev_min)

        _display_results(
            candidates=result.candidates,
            screened_date=result.screened_date,
            iev_min=result.iev_min,
            total_movers_seen=result.total_movers_seen,
            warnings=response.warnings,
            data_freshness=response.data_freshness,
            market_regime=response.market_regime,
            strategy_signals=response.strategy_signals,
            strategy_name=response.strategy_name,
        )

        # Write session sidecar for `saham trade confirm`
        _write_sidecar(
            result.candidates,
            result.screened_date,
            DEFAULT_SIDECAR_PATH,
            market_regime=response.market_regime,
        )

    except BrowserInteractionRequired as e:
        typer.echo("\nBrowser action required:", err=True)
        typer.echo(f"  URL: {e.url}", err=True)
        typer.echo(f"  {e.instructions}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Screener failed: {e}", err=True)
        raise typer.Exit(1)


def confirm_open(
    opening_json: Annotated[
        Optional[str],
        typer.Option(
            "--opening-json",
            help='Manual opening prices JSON override, e.g. {"BBCA":9050}',
        ),
    ] = None,
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
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Use headless browser for Stockbit auto-confirm"),
    ] = True,
) -> None:
    """
    Confirm pre-open candidates after the opening auction clears.

    Reads the last `saham screen pre-open` sidecar and resolves opening prices,
    then emits deterministic ENTER / WAIT / SKIP decisions. No AI is used.

    Example:
        saham trade confirm
        saham trade confirm --opening-json '{"BBCA":9050,"BMRI":5875}'
    """
    sidecar_path = session or DEFAULT_SIDECAR_PATH
    output_path = output or DEFAULT_CONFIRMATION_PATH

    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar found at '{sidecar_path}'.\n"
            "Run `saham screen pre-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    manual_prices: dict[str, Decimal] = {}
    if opening_json:
        try:
            raw_opening = json.loads(opening_json)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON in --opening-json: {e}", err=True)
            raise typer.Exit(1)

        if not isinstance(raw_opening, dict):
            typer.echo("Error: --opening-json must be a JSON object.", err=True)
            raise typer.Exit(1)

        try:
            manual_prices = {
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

    screened_at, tickers = _load_confirmation_tickers(sidecar_path)
    running_trade_provider = None
    order_book_provider = None
    missing_manual = [ticker for ticker in tickers if ticker not in manual_prices]
    auto_needed = bool(missing_manual)

    typer.echo(
        f"Confirming {len(tickers)} pre-open candidate(s) from {sidecar_path} "
        f"for {screened_at}."
    )
    if manual_prices:
        typer.echo(f"Manual opening prices supplied: {len(manual_prices)}")

    if auto_needed:
        typer.echo(
            "Resolving missing opening prices from Stockbit: "
            f"{_format_ticker_preview(missing_manual)}"
        )
        typer.echo("Tip: pass --opening-json to skip browser-backed auto resolution.")
        try:
            from src.infrastructure.browser.playwright_stockbit import (
                StockbitPlaywrightBrokerProvider,
            )
            from src.infrastructure.browser.stockbit_order_book import StockbitOrderBookProvider
            from src.infrastructure.browser.stockbit_running_trade import (
                StockbitRunningTradeProvider,
            )

            broker_provider = StockbitPlaywrightBrokerProvider(headless=headless)
            if not broker_provider.is_authenticated():
                typer.echo(
                    "No authenticated Stockbit profile for auto confirm. "
                    "Run `saham fetch stockbit login` or pass --opening-json.",
                    err=True,
                )
                raise typer.Exit(1)
            running_trade_provider = StockbitRunningTradeProvider(broker_provider=broker_provider)
            order_book_provider = StockbitOrderBookProvider(broker_provider=broker_provider)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(
                f"Auto confirm setup failed: {e}. Pass --opening-json to confirm manually.",
                err=True,
            )
            raise typer.Exit(1)

    resolver = ResolveOpeningPricesUseCase(
        running_trade_provider=running_trade_provider,
        order_book_provider=order_book_provider,
        on_observation=lambda index, total, observation: typer.echo(
            _format_opening_observation_status(index, total, observation)
        ),
    )
    observations = resolver.execute(
        ResolveOpeningPricesRequest(
            tickers=tickers,
            run_date=screened_at,
            manual_prices=manual_prices,
        )
    )
    resolved_count = sum(1 for obs in observations.values() if obs.price is not None)
    typer.echo(f"Opening prices resolved: {resolved_count}/{len(tickers)}")
    unresolved = [obs for obs in observations.values() if obs.price is None]
    if unresolved:
        typer.echo("Unresolved opening prices:")
        for obs in unresolved:
            typer.echo(f"  - {obs.ticker}: {obs.reason or 'no usable opening price'}")
    opening_prices = {
        ticker: obs.price for ticker, obs in observations.items() if obs.price is not None
    }

    screened_at, candidates, extras = _load_confirmation_candidates(
        sidecar_path,
        opening_prices,
        observations,
    )
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


def _confirm_log_impl(confirmation_path: Path, journal_path: Path) -> None:
    """Core intraday log logic — called by both the legacy subcommand and the unified trade log."""
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        intraday_entry_to_record,
    )

    if not confirmation_path.exists():
        typer.echo(
            f"No confirmation sidecar found at '{confirmation_path}'.\n"
            "Run `saham trade confirm` first.",
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

    csv_store = IntradayConfirmationCsvStore(journal_path)
    count = csv_store.append(entries)

    if count == 0:
        typer.echo(
            f"Already logged for {confirmed_at} — no new rows added ({journal_path})"
        )
    else:
        # Dual-write to unified trades.jsonl
        jsonl_store = TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl")
        for entry in entries:
            jsonl_store.append(intraday_entry_to_record(entry))
        typer.echo(f"Logged {count} confirmation(s) for {confirmed_at} → {journal_path}")


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
    Append the latest `saham trade confirm` result to the intraday confirmation journal.

    The journal is idempotent by (confirmed_at, ticker), so repeated logs for the
    same confirmation run do not duplicate rows.
    """
    _confirm_log_impl(
        confirmation_path=confirmation or DEFAULT_CONFIRMATION_PATH,
        journal_path=journal or DEFAULT_CONFIRMATION_JOURNAL_PATH,
    )


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
            "Run `saham trade log intraday` after confirming opens first.",
            err=True,
        )
        raise typer.Exit(1)

    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = IntradayConfirmationJournalService(store=store, repository=repository)
    report = service.review()
    _display_intraday_review(report, journal_path)


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
            "Run `saham trade log intraday` first.",
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




def _build_ai_researcher(provider: Optional[str] = None):
    from src.application.services.ai_research import ClaudeTickerResearcher
    if provider and provider not in ("claude", None):
        typer.echo(
            "Warning: AI research only supports 'claude' provider. Falling back.",
            err=True,
        )
    return ClaudeTickerResearcher()


def _display_intraday_backtest(response: IntradayBacktestResponse, show_trades: int) -> None:
    from src.adapters.cli.intraday_backtest_display import display_intraday_backtest
    display_intraday_backtest(response=response, show_trades=show_trades)


def intraday_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI BMRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
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

    When IEV snapshot data is available (collected via 'saham fetch iev'),
    only the top --iev-top-n movers per day are traded — matching the live workflow.
    On days without a snapshot, the full universe is screened (with a warning).
    Entries/exits use candle.open/high/low/close. All trades exit same day.

    Examples:

      saham trade backtest-intraday --universe lq45 --start 2025-12-01

      saham trade backtest-intraday BBCA BBRI BMRI ASII TLKM --start 2025-09-01

      saham trade backtest-intraday --universe lq45 --start 2025-12-01 --include-wait

      saham trade backtest-intraday --universe idx80 --start 2025-09-01 --format json
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
            "Run 'saham fetch iev' at 08:50 WIB to start collecting.",
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

    Requires an active Stockbit session (saham fetch stockbit login).

    Examples:

      saham fetch iev

      saham fetch iev --top-n 30
    """
    from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
    from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    resolved_db = db_path or DEFAULT_DB_PATH

    now_idx = _current_idx_datetime()
    today = now_idx.date()
    # Prefer Stockbit market-time API for is_ncp; fall back to wall-clock 08:56 heuristic
    _mstatus = _get_market_status()
    is_ncp = _mstatus.is_pre_open if _mstatus.source == "stockbit" else now_idx.time() >= time(8, 56)

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
        typer.echo("No movers returned — session may be expired. Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    repo = SQLiteIEVRepository(resolved_db)
    # Strip tz for naive storage; repo computes is_ncp_locked from the time component.
    written = repo.save_snapshot(today, movers, collected_at=now_idx.replace(tzinfo=None))
    try:
        sidecar_path = IEVJsonSidecarWriter().write_snapshot(
            today,
            movers,
            captured_at=now_idx,
            top_n=top_n,
        )
    except OSError as exc:
        sidecar_path = None
        typer.echo(
            typer.style(f"Warning: could not write IEV JSON sidecar: {exc}", fg=typer.colors.YELLOW),
            err=True,
        )
    deltas = repo.get_iev_delta(today)

    iep_captured = sum(1 for m in movers if m.iep is not None)
    ncp_badge = "[NCP LOCKED]" if is_ncp else "[PRE-NCP]"
    typer.echo(
        f"Saved {written} movers for {today.isoformat()} to {resolved_db} "
        f"(IEP captured: {iep_captured}/{written})"
    )
    if sidecar_path is not None:
        typer.echo(f"  JSON sidecar: {sidecar_path}")
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
