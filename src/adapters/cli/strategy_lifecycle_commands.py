"""
CLI commands for strategy lifecycle management (init, validate, list).

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.application.rules.exceptions import (
    StrategyNotFoundError,
)
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.strategy_loader import StrategyLoader

# Template for new strategy.yaml
STRATEGY_TEMPLATE = '''version: 1
name: "{name}"
description: "Strategy description goes here"

# ====================
# Indicator Definitions (optional)
# ====================
# Define custom indicator instances with specific periods.
# Built-in defaults (always available): RSI(14), SMA(20), EMA(20)

indicators:
  fast_ema:
    type: EMA
    period: 9

  slow_ema:
    type: EMA
    period: 21

# REQUIRED: Outcome when no rules match
default_outcome: MODERATE

# Optional: Map outcomes to trade actions for backtesting
signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  # EMA Crossover - bullish
  - name: bullish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "Fast EMA above slow EMA indicates bullish momentum"

  # EMA Crossover - bearish
  - name: bearish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: "<"
      right:
        indicator: slow_ema
    outcome: HIGH_RISK
    rationale: "Fast EMA below slow EMA indicates bearish momentum"

  # RSI oversold
  - name: rsi_oversold
    priority: 20
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  # RSI overbought
  - name: rsi_overbought
    priority: 20
    when:
      indicator: RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "RSI above 70 indicates overbought conditions"
'''

README_TEMPLATE = '''# {name}

{description}

## Usage

```bash
# Run backtest with this strategy
saham strategy backtest BBCA --strategy {name}

# Validate the strategy
saham strategy validate {name}
```

## Rules

This strategy uses the following rules:

1. **EMA Crossover**: Compares 9-period EMA vs 21-period EMA
2. **RSI Thresholds**: Standard overbought/oversold levels (70/30)

## Customization

Edit `strategy.yaml` to customize:
- Indicator periods
- Rule thresholds
- Signal mapping
'''


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
    # Validate name
    if "/" in name or "\\" in name:
        typer.echo("Error: Strategy name cannot contain path separators.", err=True)
        raise typer.Exit(1)

    if name.endswith(".yaml"):
        typer.echo("Error: Strategy name should not end with .yaml.", err=True)
        raise typer.Exit(1)

    # Determine target directory
    if directory:
        target_dir = directory
    else:
        target_dir = Path("strategies") / name

    strategy_yaml = target_dir / "strategy.yaml"
    readme_md = target_dir / "README.md"

    # Check if already exists
    if strategy_yaml.exists() and not force:
        typer.echo(f"Error: Strategy already exists at {strategy_yaml}", err=True)
        typer.echo("Use --force to overwrite.", err=True)
        raise typer.Exit(1)

    # Create directory
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        typer.echo(f"Error: Permission denied creating {target_dir}", err=True)
        raise typer.Exit(1)
    except OSError as e:
        typer.echo(f"Error creating directory: {e}", err=True)
        raise typer.Exit(1)

    # Write strategy.yaml
    try:
        strategy_yaml.write_text(
            STRATEGY_TEMPLATE.format(name=name),
            encoding="utf-8",
        )
    except OSError as e:
        typer.echo(f"Error writing strategy.yaml: {e}", err=True)
        raise typer.Exit(1)

    # Write README.md
    try:
        readme_md.write_text(
            README_TEMPLATE.format(name=name, description="Strategy description"),
            encoding="utf-8",
        )
    except OSError as e:
        typer.echo(f"Warning: Could not write README.md: {e}", err=True)

    typer.echo(f"Created strategy '{name}' at {target_dir}")
    typer.echo("")
    typer.echo("Files created:")
    typer.echo(f"  - {strategy_yaml}")
    typer.echo(f"  - {readme_md}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  1. Edit {strategy_yaml} to customize your strategy")
    typer.echo(f"  2. Run: saham strategy validate {name}")
    typer.echo(f"  3. Run: saham strategy backtest BBCA --strategy {name}")


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
    # Create registry for indicator validation
    registry = create_indicator_registry()
    loader = StrategyLoader(registry=registry)

    # Resolve path
    try:
        path = loader.resolve(strategy)
    except StrategyNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Validate
    result = loader.validate(path, strict=strict)

    # Display results
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

        # Generate SKILL.md after successful validation
        _generate_skill_md(path)
    else:
        typer.echo("Status: INVALID", err=True)
        typer.echo("")
        typer.echo("Errors:", err=True)
        for error in result.errors:
            typer.echo(f"  - {error}", err=True)
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
    # Create registry for validation
    registry = create_indicator_registry()
    loader = StrategyLoader(registry=registry)

    # List strategies
    strategies = loader.list_available(include_invalid=include_invalid)

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

    # Display strategies
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


def _generate_skill_md(strategy_path: Path) -> None:
    """Generate SKILL.md after successful strategy validation.

    Silently skips if no sidecar .skill.yaml exists (3rd party strategy).
    Warns on drift detection or generation issues.

    Args:
        strategy_path: Path to the validated strategy.yaml.
    """
    from src.application.services.skill_generator import SkillGeneratorService
    from src.infrastructure.skill.annotation_reader import AnnotationReader
    from src.infrastructure.skill.markdown_writer import MarkdownSkillWriter
    from src.infrastructure.skill.rules_hasher import RulesHasher

    strategy_dir = strategy_path.parent
    sidecar_path = strategy_dir / "strategy.skill.yaml"

    # Skip silently for strategies without sidecar annotations (3rd party)
    if not sidecar_path.exists():
        return

    generator = SkillGeneratorService(
        annotation_reader=AnnotationReader(),
        skill_writer=MarkdownSkillWriter(),
        rules_hasher=RulesHasher(),
    )

    result = generator.generate_for_strategy(strategy_path)

    for warning in result.warnings:
        typer.echo(f"  Warning: {warning}", err=True)

    if result.success:
        typer.echo(f"\nSKILL.md: {result.output_path}")
        if result.drift_detected:
            typer.echo(
                "  Warning: Rules changed — SKILL.md regenerated.", err=True
            )
