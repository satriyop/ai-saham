"""
CLI commands for fetching IEV snapshot data.

Layer: Adapter
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable, resolve_cli_db_path
from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    PRE_OPEN_MATCHING_START,
)
from src.infrastructure.config.app_config import load_app_config


def _current_idx_datetime() -> datetime:
    return datetime.now(IDX_TIMEZONE)


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

    Scheduled discovery runs build historical IEV data. The 08:56 run also
    supplies the locked-input baseline used by the 08:57 authoritative pre-open
    decision. Runs from 08:58 onward are diagnostic matching-period snapshots
    and cannot supply production signal evidence.

    Requires an active Stockbit session (saham fetch stockbit login).

    Examples:

      saham fetch iev

      saham fetch iev --top-n 30
    """
    from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
    from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

    cfg = load_app_config()
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)

    collection_started_at = _current_idx_datetime()
    today = collection_started_at.date()

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
        raise_data_unavailable(
            f"Error initialising Stockbit provider: {exc}",
            tip="Run: saham fetch stockbit login",
        )

    typer.echo(f"Fetching IEV snapshot (top {top_n} movers)...", err=True)
    try:
        movers = provider.fetch_iev_snapshot(top_n=top_n)
    except RuntimeError as exc:
        raise_data_unavailable(str(exc), tip="Run: saham fetch stockbit login")

    if not movers:
        raise_data_unavailable(
            "No movers returned — session may be expired.",
            tip="Run: saham fetch stockbit login",
        )

    collected_at = _current_idx_datetime()
    current_time = collected_at.time()
    is_locked_input = (
        collection_started_at.date() == collected_at.date()
        and NCP_LOCK_TIME <= collection_started_at.time()
        and collection_started_at <= collected_at
        and current_time < PRE_OPEN_MATCHING_START
    )
    repo = SQLiteIEVRepository(resolved_db)
    # Strip tz for local-naive storage; the repository validates the full interval.
    written = repo.save_snapshot(
        today,
        movers,
        collected_at=collected_at.replace(tzinfo=None),
        collection_started_at=collection_started_at.replace(tzinfo=None),
    )
    try:
        sidecar_path = IEVJsonSidecarWriter().write_snapshot(
            today,
            movers,
            captured_at=collected_at,
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
    if is_locked_input:
        phase_badge = "[NCP LOCKED INPUT]"
    elif current_time >= PRE_OPEN_MATCHING_START:
        phase_badge = "[NOT LOCKED INPUT]"
    else:
        phase_badge = "[PRE-NCP]"
    typer.echo(
        f"Saved {written} movers for {today.isoformat()} to {resolved_db} "
        f"(IEP captured: {iep_captured}/{written})"
    )
    if sidecar_path is not None:
        typer.echo(f"  JSON sidecar: {sidecar_path}")
    typer.echo(f"  Captured at {collected_at.strftime('%H:%M:%S')} WIB  {phase_badge}")
    typer.echo(
        f"  Lock-window population: top_n={top_n} "
        f"(baseline coverage is this set, not the full board)"
    )
    if is_locked_input:
        typer.echo(
            "  NCP batch: YES — is_ncp_locked=1 for this write "
            f"(collection started {collection_started_at.strftime('%H:%M:%S')} WIB)"
        )
    else:
        typer.echo(
            "  NCP batch: NO — this write is discovery/matching only. "
            "Production baseline requires a fetch started in "
            f"{NCP_LOCK_TIME.strftime('%H:%M')}–"
            f"{PRE_OPEN_MATCHING_START.strftime('%H:%M')} WIB."
        )
    typer.echo("")

    show_delta = bool(deltas)
    header = f"  {'RANK':>4}  {'TICKER':<8}  {'IEV':>12}  {'IEP':>8}"
    sep = f"  {'-' * 4}  {'-' * 8}  {'-' * 12}  {'-' * 8}"
    if show_delta:
        header += f"  {'ΔIEV DAY':>10}"
        sep += f"  {'-' * 10}"
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
    ncp = repo.get_ncp_lock_window_coverage(recent_days=14)
    typer.echo("")
    typer.echo(
        f"IEV/IEP history: {coverage['total_dates']} days "
        f"({coverage['first_date']} → {coverage['last_date']}), "
        f"avg {coverage['avg_movers_per_day']:.0f} movers/day, "
        f"IEP fill {coverage['iep_fill_pct']:.0f}%"
    )
    typer.echo(
        f"NCP lock batches: {ncp['ncp_dates']}/{ncp['history_dates']} history dates; "
        f"recent {ncp['recent_lock_batch_days']}/{ncp['recent_days_reported']} days "
        f"({ncp['recent_lock_batch_rate']:.0%}) had a lock-window batch"
    )
