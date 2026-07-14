"""
CLI commands for fetching IEV snapshot data.

Layer: Adapter
"""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config


def _current_idx_datetime() -> datetime:
    return datetime.now(IDX_TIMEZONE)


def _get_market_status():
    """Return current IDX market status from Stockbit if session available,
    else from local wall-clock. Never raises."""
    from src.infrastructure.browser.stockbit_market_time import get_current_market_status
    return get_current_market_status()


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
    to build a historical IEV dataset for the intraday proxy simulation. After
    a few months of daily collection the simulation can filter candidates by
    IEV rank, closer to live workflow behaviour.

    Requires an active Stockbit session (saham fetch stockbit login).

    Examples:

      saham fetch iev

      saham fetch iev --top-n 30
    """
    from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
    from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    now_idx = _current_idx_datetime()
    today = now_idx.date()
    # Prefer Stockbit market-time API for is_ncp; fall back to wall-clock 08:56 heuristic
    _mstatus = _get_market_status()
    is_ncp = (
        _mstatus.is_pre_open
        if _mstatus.source == "stockbit"
        else now_idx.time() >= time(8, 56)
    )

    try:
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        from src.infrastructure.browser.stockbit_config_bundle import (
            load_stockbit_provider_config,
        )
        stockbit_config = load_stockbit_provider_config()
        api_client = create_stockbit_api_client(
            headless=not no_headless, stockbit_config=stockbit_config
        )
        provider = PlaywrightStockbitProvider(
            api_client=api_client, stockbit_config=stockbit_config
        )
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
        typer.echo(
            "No movers returned — session may be expired. Run: saham fetch stockbit login",
            err=True,
        )
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
            typer.style(
                f"Warning: could not write IEV JSON sidecar: {exc}", fg=typer.colors.YELLOW
            ),
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
