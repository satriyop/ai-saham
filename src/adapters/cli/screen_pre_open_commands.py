"""
CLI commands for intraday pre-open screening.

Layer: Adapter
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.pre_open_sidecar_writer import write_pre_open_sidecar
from src.adapters.cli.screen_pre_open_display import (
    display_raw_movers,
    display_results,
    print_browser_plan,
)
from src.adapters.cli.screen_pre_open_workflow_factory import (
    create_pre_open_cli_workflow,
    resolve_pre_open_browser_plan,
    resolve_pre_open_market_status,
)
from src.application.services.pre_open_run_guard import build_pre_open_run_guard
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenWorkflowRequest,
)
from src.domain.ports.browser_data_provider import BrowserInteractionRequired
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config

_SIDECAR_ELIGIBLE_STATUSES = (
    PreOpenSourceStatus.LIVE_SUCCESS,
    PreOpenSourceStatus.EMPTY_CONFIRMED,
)


def _default_pre_open_config_path() -> Path:
    return Path(load_app_config().config_paths.pre_open_screener)


def _default_sidecar_path() -> Path:
    return Path(load_app_config().storage.intraday_sidecar)


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
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = None,
    benchmark: Annotated[
        Optional[str],
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = None,
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
    cfg = load_app_config()
    resolved_config = config_path or Path(cfg.config_paths.pre_open_screener)
    resolved_db = db_path or Path(cfg.storage.db_path)
    regime_universe = regime_universe or cfg.analysis.regime_universe
    benchmark = benchmark or cfg.analysis.benchmark

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

    run_guard = build_pre_open_run_guard(
        run_at=datetime.now(IDX_TIMEZONE),
        market_status=resolve_pre_open_market_status(),
        allow_non_trading_day=allow_non_trading_day,
    )
    if run_guard.error:
        typer.echo(f"Pre-open guard: {run_guard.error}", err=True)
        raise typer.Exit(1)

    movers_raw: list | None = None
    order_books_raw: dict | None = None
    if movers_json:
        try:
            movers_raw = json.loads(movers_json)
            if not isinstance(movers_raw, list):
                typer.echo("Error: --movers-json must be a JSON array.", err=True)
                raise typer.Exit(1)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON in --movers-json: {e}", err=True)
            raise typer.Exit(1)

        if order_books_json:
            try:
                order_books_raw = json.loads(order_books_json)
            except json.JSONDecodeError as e:
                typer.echo(f"Error: Invalid JSON in --order-books-json: {e}", err=True)
                raise typer.Exit(1)

    browser_plan = resolve_pre_open_browser_plan(
        movers_raw=movers_raw,
        order_books_raw=order_books_raw,
        headless=headless,
    )

    # A live browser fetch is skipped when outside the pre-open window and the
    # caller didn't supply --movers-json explicitly (that data is already
    # captured, live-equivalent regardless of wall-clock time). The snapshot
    # fallback below is DB-only, so it must not require a browser session.
    skip_live_fetch = run_guard.outside_window and movers_raw is None

    if browser_plan.provider is None and not skip_live_fetch:
        if browser_plan.session_missing:
            typer.echo("Playwright installed but no session found.")
            typer.echo("Run: saham fetch stockbit login")
        typer.echo("")
        typer.echo(f"Config: {resolved_config}")
        typer.echo(f"IEV threshold: {config.iev_min:,}")
        for warning in run_guard.warnings:
            typer.echo(f"Warning: {warning}")
        print_browser_plan(config)
        raise typer.Exit(0)

    if browser_plan.provider is not None and browser_plan.autonomous:
        typer.echo("Playwright session found — running autonomously...")
    elif browser_plan.provider is not None:
        top_label = f"top {config.top_n}" if config.top_n else str(len(movers_raw))
        mode_label = "fast" if config.fast_mode else "normal"
        typer.echo(
            f"Running pre-open screen ({top_label} movers, IEV >= {config.iev_min:,}, "
            f"{mode_label} mode)..."
        )
    else:
        typer.echo(
            "Outside the pre-open window and no live Stockbit session available — "
            "checking for a saved IEV snapshot..."
        )

    # Never actually called when skip_live_fetch is True: the workflow returns
    # SNAPSHOT_SUCCESS/OUTSIDE_WINDOW without touching the browser provider.
    browser_provider = browser_plan.provider or ManualBrowserDataProvider(movers=[])

    cli_workflow = create_pre_open_cli_workflow(
        resolved_db=resolved_db,
        browser_provider=browser_provider,
        with_ai=with_ai,
        ai_provider=provider,
    )
    for warning in cli_workflow.ai_warnings:
        typer.echo(warning, err=True)

    try:
        response = cli_workflow.workflow.execute(
            PreOpenWorkflowRequest(
                config=config,
                run_date=run_guard.run_at.date(),
                guard_warnings=run_guard.warnings,
                with_regime=with_regime,
                regime_universe=regime_universe,
                benchmark=benchmark,
                db_path=resolved_db,
                risk_strategy=risk_strategy,
                outside_window=skip_live_fetch,
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
            source_status=response.source_status,
            source_message=response.source_message,
            source_snapshot_path=response.source_snapshot_path,
        )

        if response.source_status in _SIDECAR_ELIGIBLE_STATUSES:
            write_pre_open_sidecar(
                candidates=result.candidates,
                screened_date=result.screened_date,
                sidecar_path=_default_sidecar_path(),
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
