"""
CLI: view broker top-foreign — universe foreign desk stock ranking cache.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_contract_cli import echo_json, resolve_output_format
from src.adapters.cli.view_broker_top_foreign_display import (
    display_broker_top_foreign_snapshots,
)
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewSubjectKind,
    ViewWindow,
    build_view_envelope,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def broker_top_foreign_view(
    snapshot_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Snapshot date (YYYY-MM-DD), default: today"),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", help="Cached look-back window used by fetch", min=1, max=365),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks to show", min=1, max=50),
    ] = 20,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Show cached foreign-broker top stock snapshots (universe scan).

    Read-only view of data from 'saham fetch broker-top-foreign'.

    Examples:
        saham view broker top-foreign --days 7
        saham view broker top-foreign --date 2024-01-15 --limit 10
        saham view broker top-foreign --format json
    """
    cfg = load_app_config()
    db_path = db_path or Path(cfg.storage.db_path)
    output_format = resolve_output_format(fmt or cfg.analysis.format or "table")
    query_date = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    repo = SQLiteBrokerRepository(db_path)
    snapshots = repo.get_foreign_flow_snapshots(query_date, period_days=days)
    if not snapshots:
        typer.echo(
            typer.style("No cached top-foreign snapshot found. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch broker-top-foreign' first."
        )
        raise typer.Exit(1)

    snapshots = snapshots[:limit]
    if output_format == "json":
        payload = [
            {
                "ticker": s.ticker,
                "snapshot_date": query_date.isoformat(),
                "period_days": days,
                "net_val": str(s.net_val),
                "net_lot": s.net_lot,
                "direction": "buy" if s.is_accumulating else "sell",
            }
            for s in snapshots
        ]
        echo_json(
            build_view_envelope(
                subject_id="universe",
                verb="top-foreign",
                status=ViewResultStatus.OK,
                as_of=query_date,
                window=ViewWindow(days=days),
                source="foreign_flow_snapshots",
                scope="universe",
                scope_note="Foreign desk universe scan cache",
                fetch_hint="saham fetch broker-top-foreign",
                subject_kind=ViewSubjectKind.DESK,
                data={"period_days": days, "limit": limit, "snapshots": payload},
            )
        )
        return

    display_broker_top_foreign_snapshots(
        snapshots=snapshots,
        query_date=query_date,
        days=days,
    )
