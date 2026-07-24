"""
CLI: view broker mappings — CSV mapping list (meta).

Layer: Adapter
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_contract_cli import echo_json, resolve_output_format
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewSubjectKind,
    build_view_envelope,
)
from src.infrastructure.csv import MappingLoader


def broker_mappings(
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    List available CSV mapping configurations.

    Mappings define how CSV columns map to expected fields.
    Create custom mappings in config/csv_mappings/
    """
    output_format = resolve_output_format(fmt or "table")
    loader = MappingLoader()
    mappings = list(loader.list_available())

    if output_format == "json":
        echo_json(
            build_view_envelope(
                subject_id="mappings",
                verb="mappings",
                status=ViewResultStatus.OK,
                data={
                    "mappings": [
                        {
                            "name": name,
                            "built_in": name == "default",
                        }
                        for name in mappings
                    ]
                },
                source="config/csv_mappings",
                scope="meta",
                subject_kind=ViewSubjectKind.DESK,
                fetch_hint="config/csv_mappings/<name>.yaml",
            )
        )
        return

    typer.echo("Available CSV Mappings:")
    typer.echo("-" * 40)

    for name in mappings:
        if name == "default":
            typer.echo(f"  {name} (built-in auto-detection)")
        else:
            typer.echo(f"  {name}")

    typer.echo("-" * 40)
    typer.echo("\nUse with: saham fetch broker-import data.csv --mapping <name>")
    typer.echo("Custom mappings: config/csv_mappings/<name>.yaml")
