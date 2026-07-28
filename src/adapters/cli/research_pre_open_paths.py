"""
Shared path and date helpers for research pre-open session commands.

Layer: Adapter
"""

from datetime import date, datetime
from pathlib import Path

import typer

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config


def opening_day_dir(run_date: date | None = None) -> Path:
    cfg = load_app_config()
    opening_data_dir = Path(cfg.storage.opening_data_dir)
    d = run_date or datetime.now(IDX_TIMEZONE).date()
    return opening_data_dir / d.strftime("%Y%m%d")


def parse_session_date(s: str | None) -> date | None:
    """Parse YYYY-MM-DD, or return None when the caller omitted a date."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        typer.echo(f"Invalid date format: {s} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)


def resolve_session_date(s: str | None) -> date:
    """Parse YYYY-MM-DD, defaulting to today in Asia/Jakarta when omitted.

    Cron and interactive pre-open commands omit --date/--session; filtering
    observations by ``None`` would match nothing (see track regression 2026-07-28).
    """
    return parse_session_date(s) or datetime.now(IDX_TIMEZONE).date()
