"""
CLI helpers for screen discovery contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable, raise_user_error
from src.application.dto.screen_contract import missing_screen_message


def resolve_output_format(fmt: str | None, *, default: str = "table") -> str:
    resolved = (fmt or default).lower()
    if resolved not in {"table", "json"}:
        raise_user_error("Invalid --format. Choose from: table, json")
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
    raise_data_unavailable(
        missing_screen_message(
            what=what,
            name=name,
            source=source,
            fetch_hint=fetch_hint,
        )
    )
