"""Shared CLI error taxonomy and exit-code contract (task 08 MVP).

Layer: Adapter only. Maps failures to operator-facing copy and exit codes.
Does not own fetch/cache/freshness policy.

Exit codes (locked product contract):
  0 — success, including valid empty results
  1 — user / input / config error (bad ticker, bad args, explicit --db missing)
  2 — data or environment unavailable (missing cache, auth, network/provider)

Valid empty must not use ``Error:`` prefix — use ``echo_cli_empty``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import NoReturn

import typer


class CliErrorCategory(str, Enum):
    """Machine-readable category label for operator messages."""

    USER_INPUT = "user_input"
    DATA_UNAVAILABLE = "data_unavailable"
    INTERNAL = "internal"


# Exit codes (keep the set small and stable).
EXIT_OK = 0
EXIT_USER = 1
EXIT_DATA = 2


def echo_cli_error(
    message: str,
    *,
    category: CliErrorCategory,
    tip: str | None = None,
    err: bool = True,
) -> None:
    """Print a standardized error line (and optional tip). Does not exit."""
    label = category.value
    typer.echo(
        typer.style(f"Error [{label}]: {message}", fg=typer.colors.RED),
        err=err,
    )
    if tip:
        typer.echo(f"Tip: {tip}", err=err)


def echo_cli_empty(message: str, *, next_step: str | None = None) -> None:
    """Print a valid-empty result (exit 0). Never uses Error: prefix."""
    typer.echo(message)
    if next_step:
        typer.echo(f"Next: {next_step}")


def raise_cli_error(
    message: str,
    *,
    category: CliErrorCategory,
    tip: str | None = None,
    exit_code: int | None = None,
) -> NoReturn:
    """Print standardized error and exit with the category's default code."""
    echo_cli_error(message, category=category, tip=tip)
    if exit_code is None:
        if category is CliErrorCategory.DATA_UNAVAILABLE:
            exit_code = EXIT_DATA
        else:
            # USER_INPUT and INTERNAL both use 1 in MVP.
            exit_code = EXIT_USER
    raise typer.Exit(exit_code)


def raise_user_error(message: str, *, tip: str | None = None) -> NoReturn:
    raise_cli_error(message, category=CliErrorCategory.USER_INPUT, tip=tip)


def raise_data_unavailable(message: str, *, tip: str | None = None) -> NoReturn:
    raise_cli_error(message, category=CliErrorCategory.DATA_UNAVAILABLE, tip=tip)


def raise_internal_error(message: str, *, tip: str | None = None) -> NoReturn:
    raise_cli_error(message, category=CliErrorCategory.INTERNAL, tip=tip)


def resolve_cli_db_path(
    db_path: Path | None,
    *,
    configured_default: Path | str,
) -> Path:
    """Resolve CLI DB path; explicit ``--db`` must already exist.

    - Explicit path: fail closed if missing (never create).
    - Configured default: may not exist yet (first-run / local-first); callers
      that open SQLite may still create the default path.
    """
    if db_path is not None:
        path = Path(db_path).expanduser()
        if not path.exists():
            raise_user_error(
                f"Database not found at {path}",
                tip="Pass an existing --db path, or omit --db to use the configured default.",
            )
        if not path.is_file():
            raise_user_error(
                f"Database path is not a file: {path}",
                tip="Pass a SQLite file path via --db.",
            )
        return path.resolve()
    return Path(configured_default).expanduser()
