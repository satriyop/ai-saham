"""
CLI commands for formula lifecycle management.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.indicator_formula_display import print_formula_list
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
    intent: Annotated[
        str, typer.Argument(help="Natural language description of the indicator")
    ],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Indicator name (e.g., SMOOTH_RSI)"),
    ] = None,
    provider: Annotated[
        str,
        typer.Option("--provider", "-p",
                      help="AI provider (deepseek/claude/openai/gemini/ollama/mock)"),
    ] = "mock",
    model: Annotated[
        Optional[str], typer.Option("--model", "-m", help="Model name for AI provider")
    ] = None,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="Save formula to storage")
    ] = True,
    formulas_path: Annotated[
        Optional[Path], typer.Option("--formulas", help="Path to formulas file")
    ] = None,
) -> None:
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
            typer.echo("\n[error] This intent cannot be expressed as a "
                       "formula.", err=True)
            typer.echo("        Tip:   Describe a mathematical combination "
                       "of indicators.", err=True)
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
            typer.echo("        Tip:   Set the API key environment "
                       f"variable for {provider}.", err=True)
        elif "connection" in msg or "timeout" in msg:
            typer.echo("[error] Could not connect to AI provider.", err=True)
            if provider == "ollama":
                typer.echo("        Tip:   Ensure Ollama is running: ollama serve", err=True)
            else:
                typer.echo("        Tip:   Check your internet connection.", err=True)
        else:
            typer.echo(f"[error] Failed to create indicator: {e}", err=True)
        raise typer.Exit(1)


def list_indicators(
    show_formulas: Annotated[
        bool, typer.Option("--formulas", "-f", help="Show formula expressions")
    ] = False,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    registry = create_indicator_registry()
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored_formulas = storage.load_all()
    print_formula_list(registry, stored_formulas, show_formulas, resolved_path)


def show(
    name: Annotated[str, typer.Argument(help="Formula name")],
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
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
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation prompt")
    ] = False,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
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
