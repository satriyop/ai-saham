"""
CLI commands for strategy creation from intent using AI translation.

Layer: Adapter
"""

import re
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import (
    raise_data_unavailable,
    raise_internal_error,
    raise_user_error,
)
from src.application.use_case.create_strategy_from_intent_use_case import (
    CreateStrategyFromIntentRequest,
    CreateStrategyFromIntentUseCase,
)
from src.infrastructure.ai.strategy_translator import StrategyTranslatorAdapter
from src.infrastructure.composition.indicator_registry_factory import create_indicator_registry
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


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
            rules_loader=RulesYamlLoader(),
        )

        response = use_case.execute(
            CreateStrategyFromIntentRequest(
                intent=intent,
                strategy_name=name,
            )
        )

        # Handle response
        if response.unsupported:
            raise_user_error(
                "This intent cannot be expressed as a strategy.",
                tip=(
                    "Unsupported: stock recommendations, price predictions, "
                    "guaranteed outcomes, non-strategy requests."
                ),
            )

        if not response.success:
            _handle_error_hints(response.error_message or "", provider)
            raise_user_error(response.error_message or "Strategy generation failed.")

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
                raise_user_error(f"Permission denied creating {target_dir}")
            except OSError as e:
                raise_data_unavailable(f"Error saving strategy: {e}")

            typer.echo(f"Strategy saved to: {strategy_yaml}")
            typer.echo("")
            typer.echo("Next steps:")
            typer.echo(f"  1. Run: saham strategy validate {response.strategy_name}")
            typer.echo(
                f"  2. Run: saham strategy backtest BBCA --strategy {response.strategy_name}"
            )
        else:
            typer.echo("Strategy not saved (--no-save specified).")
            typer.echo("")
            typer.echo("To save, run again without --no-save:")
            typer.echo(f'  saham strategy create "{intent}" --name {name}')

    except ValueError as e:
        raise_user_error(str(e))
    except Exception as e:
        error_str = str(e).lower()
        if "api key" in error_str or "authentication" in error_str:
            _handle_auth_error(provider)
            raise_data_unavailable(str(e), tip="Set the provider API key environment variable.")
        if "connection" in error_str or "timeout" in error_str:
            _handle_connection_error(provider)
            raise_data_unavailable(str(e))
        raise_internal_error(str(e))


def _slugify_intent(intent: str) -> str:
    """Convert intent to a valid strategy name slug.

    Args:
        intent: Natural language intent.

    Returns:
        A valid strategy name slug.
    """
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
