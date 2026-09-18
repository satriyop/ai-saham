"""Shared CLI output helpers (format flag + JSON echo) for contract commands.

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.adapters.cli.cli_errors import raise_user_error


def resolve_output_format(fmt: str | None, *, default: str = "table") -> str:
    """Normalize ``--format``; raise user exit on invalid values."""
    resolved = (fmt or default).lower()
    if resolved not in {"table", "json"}:
        raise_user_error("Invalid --format. Choose from: table, json")
    return resolved


def echo_json(payload: dict[str, Any] | list[Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))
