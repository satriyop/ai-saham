"""
CLI: saham research signal capture

Session-scoped authoritative observation capture for accumulation-discovery.v1.
Writes candidate_observations; does not generate forward labels.

Layer: Adapter (parse, wire, format, map errors).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.research_accum_backfill_commands import (
    _display_backfill_response,
    run_signal_observation_corpus_write,
)
from src.infrastructure.config.app_config import load_app_config


def signal_capture_observations(
    universe: Annotated[
        str,
        typer.Option("--universe", "-u", help="Universe name, e.g. lq45"),
    ],
    session: Annotated[
        str,
        typer.Option(
            "--session",
            help="Trading session date YYYY-MM-DD (single-day capture)",
        ),
    ],
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Capture canonical accumulation learning observations for one session.

    Writes database-owned schema-v1 observations. Labels are a separate step.
    """
    try:
        session_date = date.fromisoformat(session)
    except ValueError:
        typer.echo(
            "[error] Invalid --session; expected YYYY-MM-DD",
            err=True,
        )
        raise typer.Exit(1)

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    response = run_signal_observation_corpus_write(
        universe=universe,
        start_date=session_date,
        end_date=session_date,
        resolved_db=resolved_db,
    )

    if fmt == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2))
        return
    _display_backfill_response(response, title="Signal Observation Capture")
