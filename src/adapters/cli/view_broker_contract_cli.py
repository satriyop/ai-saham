"""
CLI helpers for desk-axis view broker contract (format + empty errors).

Layer: Adapter
"""

from __future__ import annotations

import json
from typing import Any

import typer

from src.application.dto.view_ticker_contract import ViewSubjectKind, build_view_envelope
from src.application.dto.view_ticker_contract import ViewResultStatus


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


def default_desk_fetch_hint() -> str:
    return "saham fetch market (Stockbit provider)"


def exit_missing_desk_data(code: str) -> None:
    typer.echo(
        typer.style(
            f"No tracked desk data for {code.upper()}.\n"
            f"Source: broker_daily_flow\n"
            f"Run: {default_desk_fetch_hint()}",
            fg=typer.colors.YELLOW,
        )
    )
    raise typer.Exit(1)


def desk_envelope(
    *,
    code: str,
    verb: str,
    data: Any,
    as_of=None,
    window=None,
    source: str = "broker_daily_flow",
    scope: str = "tracked_brokers",
    scope_note: str | None = None,
    status: ViewResultStatus = ViewResultStatus.OK,
) -> dict[str, Any]:
    return build_view_envelope(
        subject_id=code,
        verb=verb,
        status=status,
        data=data,
        as_of=as_of,
        window=window,
        source=source,
        scope=scope,
        scope_note=scope_note,
        fetch_hint=default_desk_fetch_hint(),
        subject_kind=ViewSubjectKind.DESK,
    )
