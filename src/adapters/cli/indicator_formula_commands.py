"""
CLI commands for formula lifecycle management.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.application.services.bootstrap import create_indicator_registry
from src.application.use_case.create_indicator_from_intent_use_case import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.persistence.formula_storage import (
    FormulaStorage,
    FormulaStorageError,
)

DEFAULT_FORMULAS_PATH = Path("config/formulas.yaml")


def create(
    intent: Annotated[str, typer.Argument(help="Natural language description of the indicator")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Indicator name (e.g., SMOOTH_RSI)")] = None,
    provider: Annotated[str, typer.Option("--provider", "-p", help="AI provider (deepseek/claude/openai/gemini/ollama/mock)")] = "mock",
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Model name for AI provider")] = None,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Save formula to storage")] = True,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas", help="Path to formulas file")] = None,
) -> None:
    """
    Create a custom indicator from natural language description.

    Uses AI to translate intent into a formula, validates it, and optionally saves
    it for reuse with `saham indicator compute`.

    AI Providers:
      mock      — local mock (no API key needed, for testing)
      claude    — Anthropic Claude (requires ANTHROPIC_API_KEY)
      openai    — OpenAI GPT (requires OPENAI_API_KEY)
      gemini    — Google Gemini (requires GOOGLE_API_KEY)
      ollama    — local Ollama (requires running Ollama server)

    Examples:
        saham indicator create "smoothed RSI with 14 period" --name SMOOTH_RSI
        saham indicator create "MACD line" --name MACD --provider claude
        saham indicator create "14-day RSI" --no-save
    """
    typer.echo(f"Translating: {intent!r}")
    typer.echo(f"Provider:    {provider}")

    try:
        registry = create_indicator_registry()
        available_functions = registry.get_available_indicators()
        translator = FormulaTranslatorAdapter(provider=provider, model=model)
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=available_functions,
        )
        response = use_case.execute(CreateIndicatorFromIntentRequest(
            intent=intent,
            indicator_name=name,
        ))

        if response.unsupported:
            typer.echo("\n[error] This intent cannot be expressed as a formula.", err=True)
            typer.echo("        Tip:   Describe a mathematical combination of indicators.", err=True)
            raise typer.Exit(1)

        if not response.success:
            typer.echo(f"\n[error] {response.error_message}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\nFormula: {response.formula}")

        indicator_name = name
        if not indicator_name:
            formula_clean = response.formula.replace("(", "_").replace(")", "")
            formula_clean = formula_clean.replace(",", "_").replace(" ", "")
            indicator_name = f"CUSTOM_{formula_clean[:20]}".upper()
            typer.echo(f"Auto-generated name: {indicator_name}")

        indicator_name = indicator_name.upper()

        if response.ast:
            try:
                registry.register_formula(indicator_name, response.ast)
                typer.echo(f"Registered: {indicator_name}")
            except Exception as e:
                typer.echo(f"Warning: Could not register formula in memory: {e}", err=True)

        if save and response.formula:
            resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
            storage = FormulaStorage(path=resolved_path)
            try:
                storage.save(name=indicator_name, formula=response.formula, intent=intent)
                typer.echo(f"Saved to:   {resolved_path}")
            except FormulaStorageError as e:
                typer.echo(f"Warning: Could not save formula: {e}", err=True)

        typer.echo(f"\nUse it: saham indicator compute {indicator_name} TICKER")

    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "authentication" in msg:
            typer.echo(f"[error] {e}", err=True)
            typer.echo(f"        Tip:   Set the API key environment variable for {provider}.", err=True)
        elif "connection" in msg or "timeout" in msg:
            typer.echo("[error] Could not connect to AI provider.", err=True)
            if provider == "ollama":
                typer.echo("        Tip:   Ensure Ollama is running: ollama serve", err=True)
            else:
                typer.echo("        Tip:   Check your internet connection.", err=True)
        else:
            typer.echo(f"[error] Failed to create indicator: {e}", err=True)
        raise typer.Exit(1)


def _print_formula_list(registry, stored_formulas, show_formulas, resolved_path):
    from src.application.services.indicator_registry import BUILTIN_NAMES

    console = Console()

    console.print("")
    console.print("[bold]Built-in Indicators[/bold]")
    builtin_descriptions = {
        "SMA": "Simple Moving Average",
        "EMA": "Exponential Moving Average",
        "RSI": "Relative Strength Index",
    }

    builtin_table = Table(show_header=True, header_style="bold magenta")
    builtin_table.add_column("Indicator", style="cyan")
    builtin_table.add_column("Description", style="white")
    builtin_table.add_column("Default Period", justify="right")

    for ind_name in sorted(BUILTIN_NAMES):
        desc = builtin_descriptions.get(ind_name, "")
        period = registry.get_default_period(ind_name)
        builtin_table.add_row(ind_name, desc, str(period))
    console.print(builtin_table)

    plugin_names = set(registry.list_indicators()) - BUILTIN_NAMES - set(registry.list_formulas())
    if plugin_names:
        console.print("")
        console.print("[bold]Plugin Indicators[/bold]")
        plugin_table = Table(show_header=True, header_style="bold magenta")
        plugin_table.add_column("Indicator", style="cyan")
        plugin_table.add_column("Default Period", justify="right")
        for ind_name in sorted(plugin_names):
            period = registry.get_default_period(ind_name)
            plugin_table.add_row(ind_name, str(period))
        console.print(plugin_table)

    console.print("")
    console.print("[bold]Custom Formulas[/bold]")
    if stored_formulas:
        custom_table = Table(show_header=True, header_style="bold magenta")
        custom_table.add_column("Indicator", style="cyan")
        if show_formulas:
            custom_table.add_column("Formula Expression", style="green")

        for ind_name, stored in sorted(stored_formulas.items()):
            if show_formulas:
                custom_table.add_row(ind_name, stored.formula)
            else:
                custom_table.add_row(ind_name)
        console.print(custom_table)
        console.print(f"Formulas file: {resolved_path}")
    else:
        console.print("No custom formulas saved.")
        console.print("Tip: Use `saham indicator create` to create custom indicators.")

    total = len(registry.list_indicators()) + len(stored_formulas)
    console.print(f"\nTotal available: {total}")


def list_indicators(
    show_formulas: Annotated[bool, typer.Option("--formulas", "-f", help="Show formula expressions")] = False,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    List all available indicators.

    Shows built-in indicators, loaded plugins, and saved custom formulas.
    Use --formulas to see the formula expressions for custom indicators.

    Examples:
        saham indicator list
        saham indicator list --formulas
    """
    registry = create_indicator_registry()
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored_formulas = storage.load_all()

    _print_formula_list(registry, stored_formulas, show_formulas, resolved_path)


def show(
    name: Annotated[str, typer.Argument(help="Formula name")],
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    Show details of a saved custom formula.

    Displays the formula expression, original intent, and creation date.

    Examples:
        saham indicator show SMOOTH_RSI
        saham indicator show MACD
    """
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored = storage.get(name)

    if stored is None:
        typer.echo(f"[error] Formula '{name.upper()}' not found.", err=True)
        typer.echo("\nAvailable formulas:", err=True)
        for formula_name in storage.list_names():
            typer.echo(f"  {formula_name}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nName:    {stored.name}")
    typer.echo(f"Formula: {stored.formula}")
    if stored.intent:
        typer.echo(f"Intent:  {stored.intent}")
    typer.echo(f"Created: {stored.created.strftime('%Y-%m-%d %H:%M:%S')}")


def delete(
    name: Annotated[str, typer.Argument(help="Formula name to delete")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
    formulas_path: Annotated[Optional[Path], typer.Option("--formulas-file", help="Path to formulas file")] = None,
) -> None:
    """
    Delete a saved custom formula.

    Removes the formula from persistent storage. Built-in and plugin
    indicators cannot be deleted.

    Examples:
        saham indicator delete SMOOTH_RSI
        saham indicator delete MACD --force
    """
    from src.application.services.indicator_registry import BUILTIN_NAMES

    name_upper = name.upper()

    if name_upper in BUILTIN_NAMES:
        typer.echo(f"[error] Cannot delete built-in indicator: {name_upper}", err=True)
        raise typer.Exit(1)

    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)

    if not storage.exists(name_upper):
        typer.echo(f"[error] Formula '{name_upper}' not found in storage.", err=True)
        raise typer.Exit(1)

    if not force:
        stored = storage.get(name_upper)
        typer.echo("\nFormula to delete:")
        typer.echo(f"  Name:    {stored.name}")
        typer.echo(f"  Formula: {stored.formula}")
        confirm = typer.confirm("\nDelete this formula?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(0)

    try:
        deleted = storage.delete(name_upper)
        if deleted:
            typer.echo(f"Deleted {name_upper}.")
        else:
            typer.echo(f"[error] Formula '{name_upper}' not found.", err=True)
            raise typer.Exit(1)
    except FormulaStorageError as e:
        typer.echo(f"[error] Failed to delete formula: {e}", err=True)
        raise typer.Exit(1)
