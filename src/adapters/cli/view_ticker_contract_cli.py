"""
CLI helpers for stock-axis view ticker contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.application.dto.view_ticker_contract import missing_ticker_message


def resolve_output_format(fmt: str | None, *, default: str = "table") -> str:
    """Normalize --format; raise Exit(2) on invalid values."""
    resolved = (fmt or default).lower()
    if resolved not in {"table", "json"}:
        typer.echo(
            typer.style("Invalid --format. Choose from: table, json", fg=typer.colors.RED),
            err=True,
        )
        raise typer.Exit(2)
    return resolved


def echo_json(payload: dict[str, Any] | list[Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def exit_missing_ticker_data(
    *,
    ticker: str,
    what: str,
    source: str | None = None,
    fetch_hint: str | None = None,
    for_date=None,
) -> None:
    """Print standardized missing-data message and exit 1."""
    typer.echo(
        typer.style(
            missing_ticker_message(
                ticker=ticker,
                what=what,
                source=source,
                fetch_hint=fetch_hint,
                for_date=for_date,
            ),
            fg=typer.colors.YELLOW,
        )
    )
    raise typer.Exit(1)
