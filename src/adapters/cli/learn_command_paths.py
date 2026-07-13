"""
Shared path and date helpers for learn commands.

Layer: Adapter
"""

from datetime import date, datetime
from pathlib import Path

import typer

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import APP_CFG

OPENING_DATA_DIR = Path(APP_CFG.storage.opening_data_dir)
DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_SESSION_FILE = Path(APP_CFG.storage.stockbit_session_file)
DEFAULT_PRE_OPEN_CONFIG = Path(APP_CFG.config_paths.pre_open_screener)


def opening_day_dir(run_date: date | None = None) -> Path:
    d = run_date or datetime.now(IDX_TIMEZONE).date()
    return OPENING_DATA_DIR / d.strftime("%Y%m%d")


def parse_learn_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        typer.echo(f"Invalid date format: {s} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)
