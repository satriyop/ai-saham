"""
Display helpers for strategy lifecycle CLI commands.

Layer: Adapter
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.application.dto.strategy_package import CreateStrategyPackageResponse
from src.application.services.skill_generator import SkillGenerationResult
from src.application.services.strategy_loader import StrategyInfo, ValidationResult


def print_strategy_created(response: CreateStrategyPackageResponse) -> None:
    typer.echo(f"Created strategy '{response.name}' at {response.target_dir}")
    typer.echo("")
    typer.echo("Files created:")
    typer.echo(f"  - {response.strategy_path}")
    typer.echo(f"  - {response.readme_path}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  1. Edit {response.strategy_path} to customize your strategy")
    typer.echo(f"  2. Run: saham strategy validate {response.name}")
    typer.echo(f"  3. Run: saham strategy backtest BBCA --strategy {response.name}")


def print_validation_result(path: Path, result: ValidationResult) -> None:
    typer.echo(f"Validating: {path}")
    typer.echo("")

    if result.valid:
        typer.echo("Status: VALID")
        if result.strategy_name:
            typer.echo(f"Name: {result.strategy_name}")

        if result.warnings:
            typer.echo("")
            typer.echo("Warnings:")
            for warning in result.warnings:
                typer.echo(f"  - {warning}")
    else:
        typer.echo("Status: INVALID", err=True)
        typer.echo("")
        typer.echo("Errors:", err=True)
        for error in result.errors:
            typer.echo(f"  - {error}", err=True)


def print_strategy_list(strategies: list[StrategyInfo], *, verbose: bool) -> None:
    console = Console()

    if not strategies:
        console.print("No strategies found.")
        console.print("")
        console.print("Search locations:")
        console.print("  - ./strategies/")
        console.print("")
        console.print("Create a new strategy:")
        console.print("  saham strategy init my_strategy")
        return

    console.print(f"Found {len(strategies)} strateg{'y' if len(strategies) == 1 else 'ies'}:\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Strategy", style="cyan")
    table.add_column("Display Name", style="white")

    if verbose:
        table.add_column("Description", style="white")
        table.add_column("Location", style="yellow")
        table.add_column("Status", justify="center")
        table.add_column("Path:", style="dim white")

        for info in strategies:
            status = "[green]✓ valid[/green]" if info.valid else "[red]✗ INVALID[/red]"
            disp_name = info.display_name or info.name
            desc = info.description or "-"
            table.add_row(
                info.name,
                disp_name,
                desc,
                info.location,
                status,
                str(info.path),
            )
    else:
        table.add_column("Location", style="yellow")
        table.add_column("Status", justify="center")

        for info in strategies:
            status = "[green]✓ valid[/green]" if info.valid else "[red]✗ INVALID[/red]"
            disp_name = info.display_name or info.name
            table.add_row(
                info.name,
                disp_name,
                info.location,
                status,
            )

    console.print(table)
    console.print("")
    console.print("Run 'saham strategy validate NAME' to check a strategy.")
    console.print("Run 'saham strategy backtest TICKER --strategy NAME' to use a strategy.")


def print_skill_generation_result(result: SkillGenerationResult) -> None:
    for warning in result.warnings:
        typer.echo(f"  Warning: {warning}", err=True)

    if result.success:
        typer.echo(f"\nSKILL.md: {result.output_path}")
        if result.drift_detected:
            typer.echo("  Warning: Rules changed — SKILL.md regenerated.", err=True)
