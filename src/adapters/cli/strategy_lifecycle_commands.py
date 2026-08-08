"""
CLI commands for strategy lifecycle management (init, validate, list).

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable, raise_user_error
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
            "--dir",
            "-d",
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
        raise_user_error(str(e))
    except StrategyPackageAlreadyExists as e:
        raise_user_error(
            f"Strategy already exists at {e}",
            tip="Use --force to overwrite.",
        )
    except StrategyPackageWriteError as e:
        if e.stage == "directory_permission":
            raise_user_error(f"Permission denied creating {e.path}")
        if e.stage == "directory":
            raise_data_unavailable(f"Error creating directory: {e}")
        raise_data_unavailable(f"Error writing strategy.yaml: {e}")

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
        raise_user_error(str(e), tip="Use 'saham strategy list' or path to strategy.yaml")

    result = loader.validate(path, strict=strict)

    print_validation_result(path, result)

    if result.valid:
        generate_skill_md_for_strategy(path)
    else:
        raise_user_error("Strategy validation failed.")


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
