"""
CLI commands for strategy lifecycle management (init, validate, list).

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.strategy_lifecycle_display import (
    print_strategy_created,
    print_strategy_list,
    print_validation_result,
)
from src.adapters.cli.strategy_lifecycle_factory import (
    create_strategy_loader,
    create_strategy_package_use_case,
)
from src.adapters.cli.strategy_skill_generation import generate_skill_md_for_strategy
from src.application.dto.strategy_package import CreateStrategyPackageRequest
from src.application.rules.exceptions import StrategyNotFoundError
from src.application.use_case.create_strategy_package_use_case import (
    InvalidStrategyPackageName,
    StrategyPackageAlreadyExists,
    StrategyPackageWriteError,
)


def init(
    name: Annotated[str, typer.Argument(help="Strategy name (e.g., 'momentum')")],
    directory: Annotated[
        Optional[Path],
        typer.Option(
            "--dir", "-d",
            help="Directory to create strategy in (default: ./strategies/NAME)",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing strategy"),
    ] = False,
) -> None:
    """
    Initialize a new strategy package.

    Creates a strategy folder with:
    - strategy.yaml (required)
    - README.md (documentation)

    Examples:
        saham strategy init momentum
        saham strategy init my_strategy --dir strategies/my_strategy
    """
    use_case = create_strategy_package_use_case()
    request = CreateStrategyPackageRequest(name=name, directory=directory, force=force)

    try:
        response = use_case.execute(request)
    except InvalidStrategyPackageName as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except StrategyPackageAlreadyExists as e:
        typer.echo(f"Error: Strategy already exists at {e}", err=True)
        typer.echo("Use --force to overwrite.", err=True)
        raise typer.Exit(1)
    except StrategyPackageWriteError as e:
        if e.stage == "directory_permission":
            typer.echo(f"Error: Permission denied creating {e.path}", err=True)
        elif e.stage == "directory":
            typer.echo(f"Error creating directory: {e}", err=True)
        else:
            typer.echo(f"Error writing strategy.yaml: {e}", err=True)
        raise typer.Exit(1)

    if not response.readme_written:
        typer.echo(f"Warning: Could not write README.md: {response.readme_warning}", err=True)

    print_strategy_created(response)


def validate(
    strategy: Annotated[
        str,
        typer.Argument(help="Strategy name or path to strategy.yaml"),
    ],
    strict: Annotated[
        bool,
        typer.Option("--strict", "-s", help="Treat warnings as errors"),
    ] = False,
) -> None:
    """
    Validate a strategy file.

    Checks:
    - YAML syntax
    - Required fields
    - Indicator definitions
    - Rule logic

    Examples:
        saham strategy validate momentum
        saham strategy validate ./my_strategy/strategy.yaml
        saham strategy validate momentum --strict
    """
    loader = create_strategy_loader()

    try:
        path = loader.resolve(strategy)
    except StrategyNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    result = loader.validate(path, strict=strict)

    print_validation_result(path, result)

    if result.valid:
        generate_skill_md_for_strategy(path)
    else:
        raise typer.Exit(1)


def list_strategies(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed information"),
    ] = False,
    include_invalid: Annotated[
        bool,
        typer.Option("--all", "-a", help="Include invalid strategies"),
    ] = False,
) -> None:
    """
    List available strategies.

    Shows strategies from:
    - ./strategies/ (local)

    Examples:
        saham strategy list
        saham strategy list --verbose
        saham strategy list --all
    """
    loader = create_strategy_loader()
    strategies = loader.list_available(include_invalid=include_invalid)

    print_strategy_list(strategies, verbose=verbose)
