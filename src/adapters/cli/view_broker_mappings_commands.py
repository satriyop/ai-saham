"""
CLI: view broker mappings — CSV mapping list (meta).

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.infrastructure.csv import MappingLoader


def broker_mappings() -> None:
    """
    List available CSV mapping configurations.

    Mappings define how CSV columns map to expected fields.
    Create custom mappings in config/csv_mappings/
    """
    loader = MappingLoader()
    mappings = loader.list_available()

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
