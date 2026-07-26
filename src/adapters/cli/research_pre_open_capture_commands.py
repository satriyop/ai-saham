"""
CLI: saham research pre-open capture

Save pre-open decisions into the observation database (ADR-048).
Symmetric to research signal capture for accumulation-discovery.v1:
live ``screen pre-open`` does NOT write observations.

Layer: Adapter
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.pre_open_sidecar_writer import write_pre_open_sidecar
from src.adapters.cli.research_pre_open_paths import opening_day_dir, parse_session_date
from src.adapters.cli.screen_pre_open_workflow_factory import (
    create_pre_open_cli_workflow,
    resolve_pre_open_browser_plan,
    resolve_pre_open_market_status,
)
from src.application.services.pre_open_observation_payload import (
    PRE_OPEN_OBSERVATION_CONTRACT,
)
from src.application.services.pre_open_run_guard import build_pre_open_run_guard
from src.application.use_case.opening_grade_use_case import OPENING_DATA_DIR
from src.application.use_case.pre_open_workflow_use_case import PreOpenWorkflowRequest
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.browser.stockbit_browser_provider import ManualBrowserDataProvider
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config


def pre_open_capture(
    session: Annotated[
        Optional[str],
        typer.Option(
            "--session",
            help="Session date YYYY-MM-DD (default: today)",
        ),
    ] = None,
    movers_json: Annotated[
        Optional[str],
        typer.Option(
            "--movers-json",
            help="Discovery-only manual input; rejected by authoritative capture",
        ),
    ] = None,
    order_books_json: Annotated[
        Optional[str],
        typer.Option(
            "--order-books-json",
            help="Discovery-only manual input; rejected by authoritative capture",
        ),
    ] = None,
    top: Annotated[
        Optional[int],
        typer.Option("--top", help="Process only top N movers by IEV"),
    ] = None,
    fast: Annotated[
        bool,
        typer.Option("--fast/--no-fast", help="Skip order book fetches"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Pre-open screener config YAML"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless"),
    ] = True,
    allow_non_trading_day: Annotated[
        bool,
        typer.Option(
            "--allow-non-trading-day",
            help="Allow weekend/non-trading-day capture",
        ),
    ] = False,
    no_regime: Annotated[
        bool,
        typer.Option("--no-regime", help="Skip regime evaluation"),
    ] = False,
    no_risk: Annotated[
        bool,
        typer.Option("--no-risk", help="Skip risk assessment"),
    ] = False,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Save pre-open decisions into candidate_observations (screen_pre_open).

    Sole decision authority write for the opening learning loop (clean break).
    Also writes same-run ops packaging: data/opening/YYYYMMDD/ops_session.json
    and trade-confirm sidecar. Does not generate open_30m labels
    (use ``research pre-open labels``).

    Examples:
        saham research pre-open capture
        saham research pre-open capture --fast

    Capture requires the direct live provider and fails closed unless its whole
    collection stays inside the same-session 08:56–08:58 locked-input window
    and finishes before matching. Manual mover payloads and saved snapshots are
    not authoritative.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    resolved_config = config_path or Path(cfg.config_paths.pre_open_screener)
    run_date = parse_session_date(session)

    overrides: dict = {
        "top_n": top,
        "fast_mode": fast or None,
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

    if movers_json is not None or order_books_json is not None:
        typer.echo(
            "Capture rejected: manual JSON is discovery-only. Use "
            "`saham screen pre-open` for manual payloads; authoritative capture "
            "requires the direct live provider.",
            err=True,
        )
        raise typer.Exit(1)

    movers_raw: list | None = None
    order_books_raw: dict | None = None

    browser_plan = resolve_pre_open_browser_plan(
        movers_raw=movers_raw,
        order_books_raw=order_books_raw,
        headless=headless,
    )
    skip_live_fetch = run_guard.outside_window and movers_raw is None
    if browser_plan.provider is None and not skip_live_fetch:
        typer.echo(
            "Browser/session plan required for capture (or pass --movers-json / "
            "run inside window with snapshot fallback).",
            err=True,
        )
        if browser_plan.session_missing:
            typer.echo("Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    browser_provider = browser_plan.provider or ManualBrowserDataProvider(movers=[])
    cli_workflow = create_pre_open_cli_workflow(
        resolved_db=resolved_db,
        browser_provider=browser_provider,
        with_ai=False,
        ai_provider=None,
    )
    if cli_workflow.record_observations_use_case is None:
        typer.echo("Error: observation recorder not wired.", err=True)
        raise typer.Exit(1)

    workflow_request = PreOpenWorkflowRequest(
        config=config,
        run_date=run_date,
        guard_warnings=run_guard.warnings,
        regime_enabled=not no_regime,
        risk_enabled=not no_risk,
        signal_enabled=True,
        regime_universe=cfg.analysis.regime_universe,
        benchmark=cfg.analysis.benchmark,
        db_path=resolved_db,
        outside_window=skip_live_fetch,
        is_trading_day=run_guard.is_trading_day,
    )

    try:
        result = cli_workflow.record_observations_use_case.execute(
            workflow_request,
            opening_data_dir=OPENING_DATA_DIR,
        )
    except Exception as e:
        typer.echo(f"Capture failed: {e}", err=True)
        raise typer.Exit(1)

    # Same-run trade-confirm sidecar (ops packaging; not decision authority)
    try:
        sidecar_path = Path(cfg.storage.intraday_sidecar)
        write_pre_open_sidecar(
            candidates=list(result.response.result.candidates),
            screened_date=result.response.result.screened_date,
            sidecar_path=sidecar_path,
            market_regime=result.response.market_regime,
        )
    except Exception as e:
        typer.echo(f"Warning: trade-confirm sidecar not written: {e}", err=True)

    day = opening_day_dir(run_date)
    payload = {
        "artifact_type": "pre_open_observation_capture",
        "session": run_date.isoformat(),
        "recorded_count": result.recorded_count,
        "candidate_count": len(result.response.result.candidates),
        "filter_reject_count": len(result.response.filter_rejects),
        "source_status": result.response.source_status.value,
        "workflow": "screen_pre_open",
        "observation_contract": PRE_OPEN_OBSERVATION_CONTRACT,
        "ops_export_path": result.ops_export_path,
        "ops_day_dir": str(day),
    }
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo("Pre-open observation capture")
    typer.echo(f"  session:           {payload['session']}")
    typer.echo(f"  recorded:          {payload['recorded_count']}")
    typer.echo(f"  candidates:        {payload['candidate_count']}")
    typer.echo(f"  filter_rejects:    {payload['filter_reject_count']}")
    typer.echo(f"  source_status:     {payload['source_status']}")
    typer.echo(f"  contract:          {PRE_OPEN_OBSERVATION_CONTRACT}")
    if result.ops_export_path:
        typer.echo(f"  ops export:        {result.ops_export_path}")
    typer.echo(
        "  Next: research pre-open track → research pre-open grade | research pre-open labels"
    )
