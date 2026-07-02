"""
CLI commands for intraday pre-open screening.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.screen_pre_open_display import (
    display_raw_movers,
    display_results,
)
from src.application.services.bootstrap import create_indicator_registry
from src.domain.value_objects.market_context import MarketContext
from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenUseCase,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenWorkflowRequest,
    PreOpenWorkflowUseCase,
)
from src.domain.ports.browser_data_provider import BrowserInteractionRequired
from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    PRE_OPEN_START,
)
from src.domain.value_objects.idx_market import (
    REGULAR_OPEN as PRE_OPEN_END,
)
from src.domain.value_objects.screener_result import ScreenerCandidate
from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.market_context_factory import evaluate_market_context
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_PRE_OPEN_CONFIG_PATH = Path(APP_CFG.config_paths.pre_open_screener)
DEFAULT_SESSION_FILE = Path(APP_CFG.storage.stockbit_session_file)
DEFAULT_SIDECAR_PATH = Path(APP_CFG.storage.intraday_sidecar)
DEFAULT_REGIME_UNIVERSE = APP_CFG.analysis.regime_universe
DEFAULT_REGIME_BENCHMARK = APP_CFG.analysis.benchmark


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


def _get_market_status():
    """Return current IDX market status from Stockbit if session available,
    else from local wall-clock. Never raises."""
    from src.infrastructure.browser.stockbit_market_time import get_current_market_status

    return get_current_market_status()


def _build_intraday_run_guard(
    run_at: datetime,
    allow_non_trading_day: bool = False,
    market_status=None,
) -> IntradayRunGuard:
    warnings: list[str] = []
    local_run_at = run_at.astimezone(IDX_TIMEZONE)

    status = market_status or _get_market_status()
    if status.source == "stockbit":
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
        # Heuristic/wall-clock fallback
        is_weekend = local_run_at.weekday() in (5, 6)
        if is_weekend:
            message = (
                f"{local_run_at.date()} is a weekend. "
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


def _write_sidecar(
    candidates: list[ScreenerCandidate],
    screened_date: date,
    sidecar_path: Path,
    market_regime: "MarketContext | None" = None,
) -> None:
    """Write session sidecar JSON so `saham trade confirm` can read it."""
    import json

    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "artifact_type": "pre_open_session",
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
                "opening_broker_backing_tag": c.opening_broker_backing_tag,
                "opening_broker_backing_score": c.opening_broker_backing_score,
                "opening_broker_buy_streak": c.opening_broker_buy_streak,
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


def pre_open(
    movers_json: Annotated[
        Optional[str],
        typer.Option("--movers-json", help="Pre-fetched movers JSON array"),
    ] = None,
    order_books_json: Annotated[
        Optional[str],
        typer.Option("--order-books-json", help="Pre-fetched order books JSON object"),
    ] = None,
    iev_min: Annotated[Optional[int], typer.Option("--iev-min", min=1)] = None,
    iep_min: Annotated[
        Optional[int],
        typer.Option(
            "--iep-min",
            min=1,
            help="IEP floor: exclude movers with IEP below this (IDR)",
        ),
    ] = None,
    capital: Annotated[Optional[int], typer.Option("--capital", min=1)] = None,
    stop_loss: Annotated[Optional[float], typer.Option("--stop-loss")] = None,
    tick_above: Annotated[Optional[int], typer.Option("--tick-above", min=1)] = None,
    top: Annotated[
        Optional[int],
        typer.Option("--top", help="Process only top N movers by IEV"),
    ] = None,
    fast: Annotated[
        bool,
        typer.Option("--fast/--no-fast", help="Skip order book fetches"),
    ] = False,
    max_gap: Annotated[
        Optional[float],
        typer.Option("--max-gap", help="Override max gap % threshold"),
    ] = None,
    atr_mult: Annotated[
        Optional[float],
        typer.Option("--atr-mult", help="Override ATR stop multiplier"),
    ] = None,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Pre-open screener config YAML path"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    with_ai: Annotated[
        bool,
        typer.Option("--with-ai", help="Enable AI research"),
    ] = False,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Add market regime context"),
    ] = False,
    regime_universe: Annotated[
        str,
        typer.Option("--regime-universe", help="Universe for regime breadth"),
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
            help="Allow weekend/non-trading-day dry-runs",
        ),
    ] = False,
    risk_strategy: Annotated[
        Optional[str],
        typer.Option(
            "--risk-strategy",
            help="Strategy/rules name to show as an extra risk-status column",
        ),
    ] = None,
) -> None:
    """
    Run the pre-open market screener for IDX stocks.

    Outputs conditional entry ranges (not fixed prices) aligned to the IDX
    call auction mechanism. Enter at open only if opening price falls within
    the displayed range.
    """
    import json

    resolved_config = config_path or DEFAULT_PRE_OPEN_CONFIG_PATH
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
    config = load_pre_open_screen_config(resolved_config, overrides)
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
            from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider

            browser_provider = PlaywrightStockbitProvider(
                profile_dir=Path(APP_CFG.storage.stockbit_profile_dir),
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
            from src.adapters.cli.screen_pre_open_display import print_browser_plan

            print_browser_plan(config)
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
            from src.application.services.ai_research import ClaudeTickerResearcher

            if provider and provider not in ("claude", None):
                typer.echo(
                    "Warning: AI research only supports 'claude' provider. Falling back.",
                    err=True,
                )
            ai_explainer = ClaudeTickerResearcher()
        except Exception as e:
            typer.echo(f"Warning: Could not initialize AI research: {e}", err=True)

    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider

    notation_provider = StockbitTickerNotationProvider(api_client=None, db_path=resolved_db)

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
        evaluate_market_context=evaluate_market_context,
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
                risk_strategy=risk_strategy,
            )
        )
        result = response.result

        if not movers_json and getattr(response, "raw_movers", None):
            display_raw_movers(response.raw_movers, config.top_n, config.iev_min)

        display_results(
            candidates=result.candidates,
            screened_date=result.screened_date,
            iev_min=result.iev_min,
            total_movers_seen=result.total_movers_seen,
            warnings=response.warnings,
            data_freshness=response.data_freshness,
            market_regime=response.market_regime,
            strategy_risk_statuses=response.strategy_risk_statuses,
            risk_strategy_name=response.risk_strategy_name,
        )

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
