"""
CLI helpers for screen discovery contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.application.dto.screen_contract import missing_screen_message


def resolve_output_format(fmt: str | None, *, default: str = "table") -> str:
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


def exit_missing_screen_data(
    *,
    what: str,
    name: str | None = None,
    source: str | None = None,
    fetch_hint: str | None = None,
) -> None:
    typer.echo(
        typer.style(
            missing_screen_message(
                what=what,
                name=name,
                source=source,
                fetch_hint=fetch_hint,
            ),
            fg=typer.colors.YELLOW,
        )
    )
    raise typer.Exit(1)
