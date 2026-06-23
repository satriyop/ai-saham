"""
CLI commands for strategy management.

Provides commands to init, validate, list, and create strategy packages.

Layer: Adapter
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.adapters.cli.strategy_skill_commands import skill_app
from src.application.rules.exceptions import (
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
    StrategyNotFoundError,
)
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.strategy_loader import StrategyLoader
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.application.use_case.create_strategy_from_intent_use_case import (
    CreateStrategyFromIntentRequest,
    CreateStrategyFromIntentUseCase,
)
from src.infrastructure.ai.strategy_translator import StrategyTranslatorAdapter
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

# Create Typer sub-app for strategy commands
strategy_app = typer.Typer(
    name="strategy",
    help="Manage strategy packages (init, validate, list)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
strategy_app.add_typer(skill_app, name="skill")

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


@strategy_app.command("init")
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


@strategy_app.command("validate")
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


@strategy_app.command("list")
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
        table.add_column("Path:", style="dim white")  # Colon required for test contract!

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


@strategy_app.command("create")
def create(
    intent: Annotated[
        str,
        typer.Argument(help="Natural language strategy description"),
    ],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Strategy name (default: derived from intent)"),
    ] = None,
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="AI provider (claude, openai, gemini, ollama, mock)"),
    ] = "mock",
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model name (for Ollama)"),
    ] = None,
    directory: Annotated[
        Optional[Path],
        typer.Option("--dir", "-d", help="Directory to save strategy (default: ./strategies/NAME)"),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save/--no-save", help="Save to file (default: save)"),
    ] = True,
) -> None:
    """
    Create a strategy from natural language description using AI.

    Generates a complete strategy.yaml from your description and validates
    that it's correct before saving.

    Examples:
        saham strategy create "RSI oversold strategy" --name oversold_rsi
        saham strategy create "EMA crossover with 9 and 21 periods" -n ema_cross
        saham strategy create "conservative momentum strategy" --provider claude
        saham strategy create "MACD crossover" --no-save  # Preview only
    """
    # Derive strategy name from intent if not provided
    if not name:
        # Create a simple slug from intent
        name = _slugify_intent(intent)

    typer.echo("Creating strategy from intent...")
    typer.echo("")

    try:
        # Initialize components
        registry = create_indicator_registry()
        translator = StrategyTranslatorAdapter(
            provider=provider,
            model=model,
        )

        # Execute use case
        use_case = CreateStrategyFromIntentUseCase(
            translator=translator,
            registry=registry,
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent=intent,
                strategy_name=name,
            )
        )

        # Handle response
        if response.unsupported:
            typer.echo("Error: This intent cannot be expressed as a strategy.", err=True)
            typer.echo("", err=True)
            typer.echo("Unsupported requests include:", err=True)
            typer.echo("  - Specific stock recommendations", err=True)
            typer.echo("  - Price predictions", err=True)
            typer.echo("  - Guaranteed outcomes", err=True)
            typer.echo("  - Non-strategy requests", err=True)
            raise typer.Exit(1)

        if not response.success:
            typer.echo(f"Error: {response.error_message}", err=True)
            _handle_error_hints(response.error_message or "", provider)
            raise typer.Exit(1)

        # Display generated strategy
        typer.echo("Generated Strategy:")
        typer.echo("─" * 50)
        typer.echo(response.yaml_content)
        typer.echo("─" * 50)
        typer.echo("")

        # Save if requested
        if save:
            # Determine target directory
            if directory:
                target_dir = directory
            else:
                target_dir = Path("strategies") / response.strategy_name

            strategy_yaml = target_dir / "strategy.yaml"

            # Check if already exists
            if strategy_yaml.exists():
                typer.echo(f"Warning: Strategy already exists at {strategy_yaml}", err=True)
                if not typer.confirm("Overwrite?"):
                    typer.echo("Aborted.")
                    raise typer.Exit(0)

            # Create directory and save
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                strategy_yaml.write_text(response.yaml_content, encoding="utf-8")
            except PermissionError:
                typer.echo(f"Error: Permission denied creating {target_dir}", err=True)
                raise typer.Exit(1)
            except OSError as e:
                typer.echo(f"Error saving strategy: {e}", err=True)
                raise typer.Exit(1)

            typer.echo(f"Strategy saved to: {strategy_yaml}")
            typer.echo("")
            typer.echo("Next steps:")
            typer.echo(f"  1. Run: saham strategy validate {response.strategy_name}")
            typer.echo(f"  2. Run: saham strategy backtest BBCA --strategy {response.strategy_name}")
        else:
            typer.echo("Strategy not saved (--no-save specified).")
            typer.echo("")
            typer.echo("To save, run again without --no-save:")
            typer.echo(f'  saham strategy create "{intent}" --name {name}')

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_str = str(e).lower()
        if "api key" in error_str or "authentication" in error_str:
            _handle_auth_error(provider)
        elif "connection" in error_str or "timeout" in error_str:
            _handle_connection_error(provider)
        else:
            typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def _slugify_intent(intent: str) -> str:
    """Convert intent to a valid strategy name slug.

    Args:
        intent: Natural language intent.

    Returns:
        A valid strategy name slug.
    """
    import re

    # Take first few words
    words = intent.lower().split()[:4]
    slug = "_".join(words)

    # Remove non-alphanumeric characters except underscore
    slug = re.sub(r"[^a-z0-9_]", "", slug)

    # Ensure it doesn't start with a number
    if slug and slug[0].isdigit():
        slug = "strategy_" + slug

    # Fallback if empty
    if not slug:
        slug = "generated_strategy"

    return slug


def _handle_error_hints(error_message: str, provider: str) -> None:
    """Display helpful hints based on error message."""
    error_lower = error_message.lower()

    if "api key" in error_lower or "authentication" in error_lower:
        _handle_auth_error(provider)
    elif "timeout" in error_lower:
        _handle_connection_error(provider)
    elif "invalid yaml" in error_lower or "schema" in error_lower:
        typer.echo("", err=True)
        typer.echo("The AI generated invalid YAML. Try:", err=True)
        typer.echo("  - Rephrasing your intent more clearly", err=True)
        typer.echo("  - Using simpler language", err=True)
        typer.echo("  - Using a different AI provider", err=True)


def _handle_auth_error(provider: str) -> None:
    """Display helpful message for authentication errors."""
    env_vars = {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    typer.echo("", err=True)
    if provider in env_vars:
        typer.echo(f"Set {env_vars[provider]} environment variable.", err=True)
    else:
        typer.echo("Check your API configuration.", err=True)


def _handle_connection_error(provider: str) -> None:
    """Display helpful message for connection errors."""
    typer.echo("", err=True)
    if provider == "ollama":
        typer.echo("Is Ollama running? Start with: ollama serve", err=True)
    else:
        typer.echo("Check your internet connection.", err=True)


DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


@strategy_app.command("backtest")
def backtest(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    strategy: Annotated[
        Optional[str],
        typer.Option("--strategy", "-S", help="Strategy name or path (e.g., 'momentum')"),
    ] = None,
    rules_file: Annotated[
        Optional[Path],
        typer.Option("--rules-file", "-r", help="Path to YAML rules file (backward-compatible)"),
    ] = None,
    start: Annotated[Optional[str], typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)")] = APP_CFG.backtest.start_date,
    end: Annotated[Optional[str], typer.Option("--end", "-e", help="End date (YYYY-MM-DD)")] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = APP_CFG.trading.capital,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show trade-by-trade output")] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="Path to SQLite database")] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = APP_CFG.analysis.format,
) -> None:
    """
    Backtest a strategy against historical data.

    Runs a deterministic simulation using rules from a strategy package or YAML file.
    Replays historical candles and applies rules per candle to generate signals.

    Strategy Resolution:
        --strategy resolves name as:
          1. ./NAME/strategy.yaml
          2. ./strategies/NAME/strategy.yaml

    Signal Mapping (customizable in YAML):
        LOW_RISK  → ENTER_LONG (buy)
        MODERATE  → HOLD
        HIGH_RISK → EXIT_LONG (sell)

    Examples:
        saham strategy backtest BBCA --strategy momentum
        saham strategy backtest BBCA -S ./strategies/momentum/strategy.yaml
        saham strategy backtest BBRI -S momentum --start 2024-01-01
        saham strategy backtest TLKM -S momentum --capital 50000000 --verbose
    """
    from datetime import datetime

    if not strategy and not rules_file:
        typer.echo("[error] Either --strategy or --rules-file is required.", err=True)
        typer.echo("        Fix:   saham strategy backtest BBCA --strategy momentum", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH

    start_date = None
    end_date = None
    try:
        if start:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        typer.echo("[error] Invalid date format. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(1)

    broker_repository = SQLiteBrokerRepository(resolved_db)

    if strategy:
        registry = create_indicator_registry(broker_repository=broker_repository)
        loader = StrategyLoader(registry=registry)
        try:
            resolved_rules_path = loader.resolve(strategy)
            strategy_display = strategy
        except StrategyNotFoundError as e:
            typer.echo(f"[error] {e}", err=True)
            raise typer.Exit(1)
    else:
        resolved_rules_path = rules_file  # type: ignore
        strategy_display = str(rules_file)

    typer.echo(f"Backtesting {ticker.upper()} with strategy '{strategy_display}'...")

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        registry = create_indicator_registry(
            broker_repository=broker_repository,
            market_repository=repository,
        )
        use_case = BacktestUseCase(repository=repository, registry=registry)
        response = use_case.execute(BacktestRequest(
            ticker=ticker,
            rules_file=resolved_rules_path,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(capital)),
        ))
        result = response.result

        if fmt == "json":
            import json as _json
            typer.echo(_json.dumps(result.to_dict(), indent=2))
            return

        typer.echo(f"\n{'='*52}")
        typer.echo(f" Backtest Results  ·  {result.ticker}  ·  {result.strategy_name}")
        typer.echo(f"{'='*52}\n")
        typer.echo(f"Period: {result.start_date} → {result.end_date}")

        typer.echo("\nPerformance")
        typer.echo(f"{'─'*40}")
        typer.echo(f"  Initial Capital:  {result.initial_capital:>18,.0f} IDR")
        typer.echo(f"  Final Capital:    {result.final_capital:>18,.0f} IDR")
        typer.echo(f"  Total Return:     {result.total_return_pct:>18.2f}%")
        typer.echo(f"  Max Drawdown:     {result.max_drawdown_pct:>18.2f}%")

        typer.echo("\nTrade Statistics")
        typer.echo(f"{'─'*40}")
        typer.echo(f"  Total Trades:     {result.trade_count:>18}")
        typer.echo(f"  Winning Trades:   {result.winning_trades:>18}")
        typer.echo(f"  Losing Trades:    {result.losing_trades:>18}")
        typer.echo(f"  Win Rate:         {result.win_rate:>18.2f}%")
        typer.echo(f"  Profit Factor:    {result.profit_factor:>18.2f}")
        if result.trades:
            typer.echo(f"  Avg Win:          {result.avg_win:>18,.0f} IDR")
            typer.echo(f"  Avg Loss:         {result.avg_loss:>18,.0f} IDR")

        if verbose and result.trades:
            typer.echo("\nTrade History")
            typer.echo("─" * 80)
            typer.echo(
                f"{'#':<4} {'Entry':<12} {'Exit':<12} {'Entry Price':>12}"
                f" {'Exit Price':>12} {'P&L':>14} {'%':>8}"
            )
            typer.echo("─" * 80)
            for i, trade in enumerate(result.trades, 1):
                sign = "+" if trade.pnl >= 0 else ""
                typer.echo(
                    f"{i:<4} {str(trade.entry_date):<12} {str(trade.exit_date):<12}"
                    f" {trade.entry_price:>12,.0f} {trade.exit_price:>12,.0f}"
                    f" {sign}{trade.pnl:>13,.0f} {trade.pnl_percent:>7.2f}%"
                )
            typer.echo("─" * 80)
            typer.echo(f"\nEntry Rules: {', '.join(set(t.entry_rule for t in result.trades))}")
            typer.echo(f"Exit Rules:  {', '.join(set(t.exit_rule for t in result.trades))}")

        typer.echo(f"\n{'='*52}")
        typer.echo("\nDISCLAIMER: Historical simulation only, not trading advice.")

    except StrategyNotFoundError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except RulesFileError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except RulesSchemaError as e:
        typer.echo(f"[error] Rules schema error: {e}", err=True)
        raise typer.Exit(1)
    except RulesValidationError as e:
        typer.echo(f"[error] Invalid rules: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"[error] Database not found at {resolved_db}.", err=True)
        typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            typer.echo(f"[error] No cached data for {ticker.upper()}.", err=True)
            typer.echo(f"        Fix:   saham fetch market {ticker.upper()} --days 365", err=True)
        else:
            typer.echo(f"[error] Backtest failed: {e}", err=True)
        raise typer.Exit(1)


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
