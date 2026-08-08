"""
CLI helpers for stock-axis view ticker contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable, raise_user_error
from src.application.dto.view_ticker_contract import (
    default_ticker_fetch_hint,
    missing_ticker_message,
)


def resolve_output_format(fmt: str | None, *, default: str = "table") -> str:
    """Normalize --format; raise user exit on invalid values."""
    resolved = (fmt or default).lower()
    if resolved not in {"table", "json"}:
        raise_user_error("Invalid --format. Choose from: table, json")
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
    """Print standardized missing-data message and exit as data_unavailable."""
    hint = fetch_hint or default_ticker_fetch_hint(ticker)
    message = missing_ticker_message(
        ticker=ticker,
        what=what,
        source=source,
        fetch_hint=hint,
        for_date=for_date,
    )
    # First line is the operator summary; full multi-line body stays in message.
    raise_data_unavailable(message)
