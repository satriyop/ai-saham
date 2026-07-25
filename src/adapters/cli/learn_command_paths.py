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


def parse_learn_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        typer.echo(f"Invalid date format: {s} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)
