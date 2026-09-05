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

from src.adapters.cli.cli_errors import (
    raise_data_unavailable,
    raise_internal_error,
    raise_user_error,
    resolve_cli_db_path,
)
from src.adapters.cli.research_pre_open_paths import parse_session_date
from src.adapters.cli.screen_pre_open_workflow_factory import (
    create_pre_open_cli_workflow,
    has_same_day_auction_evidence,
    resolve_pre_open_browser_plan,
    resolve_pre_open_market_status,
)
from src.application.services.pre_open_observation_payload import (
    PRE_OPEN_OBSERVATION_CONTRACT,
)
from src.application.services.pre_open_run_guard import build_pre_open_run_guard
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
    Save pre-open decisions into database-owned learning observations.

    Sole decision authority write for the opening learning loop (clean break).
    Does not write trade-confirm sidecars. Does not generate open_30m labels
    (use ``research pre-open labels``). Post-open assess: ``saham assess pre-open``.

    Examples:
        saham research pre-open capture
        saham research pre-open capture --fast

    Capture requires the direct live provider and fails closed unless its whole
    collection stays inside the same-session 08:56–08:58 locked-input window
    and finishes before matching. Manual mover payloads and saved snapshots are
    not authoritative.
    """
    cfg = load_app_config()
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)
    resolved_config = config_path or Path(cfg.config_paths.pre_open_screener)
    run_date = parse_session_date(session)

    overrides: dict = {
        "top_n": top,
        "fast_mode": fast or None,
    }
    config = load_pre_open_screen_config(resolved_config, overrides)

    run_at = datetime.now(IDX_TIMEZONE)
    run_guard = build_pre_open_run_guard(
        run_at=run_at,
        market_status=resolve_pre_open_market_status(),
        allow_non_trading_day=allow_non_trading_day,
        same_day_auction_evidence=has_same_day_auction_evidence(
            resolved_db,
            run_date or run_at.date(),
        ),
    )
    if run_guard.error:
        raise_user_error(f"Pre-open guard: {run_guard.error}")

    if movers_json is not None or order_books_json is not None:
        raise_user_error(
            "Capture rejected: manual JSON is discovery-only.",
            tip=(
                "Use `saham screen pre-open` for manual payloads; "
                "authoritative capture requires the direct live provider."
            ),
        )

    movers_raw: list | None = None
    order_books_raw: dict | None = None

    browser_plan = resolve_pre_open_browser_plan(
        movers_raw=movers_raw,
        order_books_raw=order_books_raw,
        headless=headless,
    )
    skip_live_fetch = run_guard.outside_window and movers_raw is None
    if browser_plan.provider is None and not skip_live_fetch:
        tip = (
            "Run: saham fetch stockbit login"
            if browser_plan.session_missing
            else "Run inside the pre-open window or after stockbit login."
        )
        raise_data_unavailable(
            "Browser/session plan required for capture.",
            tip=tip,
        )

    browser_provider = browser_plan.provider or ManualBrowserDataProvider(movers=[])
    cli_workflow = create_pre_open_cli_workflow(
        resolved_db=resolved_db,
        browser_provider=browser_provider,
        with_ai=False,
        ai_provider=None,
    )
    if cli_workflow.record_observations_use_case is None:
        raise_internal_error("observation recorder not wired.")

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
        )
    except Exception as e:
        raise_data_unavailable(f"Capture failed: {e}")

    observation_rows = [
        {
            "observation_id": row.observation_id,
            "ticker": row.ticker,
            "screen_result": row.screen_result,
            "inserted": row.inserted,
        }
        for row in result.observations
    ]
    session = (
        run_date.isoformat() if run_date is not None else str(result.response.result.screened_date)
    )
    payload = {
        "artifact_type": "pre_open_observation_capture",
        "session": session,
        "recorded_count": result.recorded_count,
        "candidate_count": len(result.response.result.candidates),
        "filter_reject_count": len(result.response.filter_rejects),
        "source_status": result.response.source_status.value,
        "workflow": "screen_pre_open",
        "observation_contract": PRE_OPEN_OBSERVATION_CONTRACT,
        "observations": observation_rows,
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
    if observation_rows:
        typer.echo("  observations:")
        for row in observation_rows:
            flag = "new" if row["inserted"] else "exists"
            typer.echo(
                f"    {row['ticker']:6}  {row['observation_id']}  "
                f"{row['screen_result'] or '-'}  ({flag})"
            )
    typer.echo("  Next: research pre-open track → analyze pre-open → labels → evaluate")
    typer.echo(
        "  Analyze: saham assess pre-open --observation-id <id> [--opening-snapshot-id <id>]"
    )
