"""
CLI commands for formula lifecycle management.

Layer: Adapter

Thin: parse args, call application use cases, format output, map errors, and
handle user confirmation. Persistence and policy live in the use cases; infra
wiring lives in ``indicator_formula_factory``.
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.indicator_formula_display import print_formula_list
from src.adapters.cli.indicator_formula_factory import (
    create_delete_formula_use_case,
    create_formula_authoring_use_cases,
    create_list_formulas_use_case,
    create_show_formula_use_case,
    resolve_formulas_path,
)
from src.application.ports.formula_store import FormulaStoreError
from src.application.use_case.create_indicator_from_intent_use_case import (
    CreateIndicatorFromIntentRequest,
)
from src.application.use_case.delete_formula_use_case import DeleteEligibility
from src.application.use_case.persist_generated_formula_use_case import (
    PersistGeneratedFormulaRequest,
)


def create(
    intent: Annotated[str, typer.Argument(help="Natural language description of the indicator")],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Indicator name (e.g., SMOOTH_RSI)"),
    ] = None,
    provider: Annotated[
        str,
        typer.Option(
            "--provider", "-p", help="AI provider (deepseek/claude/openai/gemini/ollama/mock)"
        ),
    ] = "mock",
    model: Annotated[
        Optional[str], typer.Option("--model", "-m", help="Model name for AI provider")
    ] = None,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Save formula to storage")] = True,
    formulas_path: Annotated[
        Optional[Path], typer.Option("--formulas", help="Path to formulas file")
    ] = None,
) -> None:
    typer.echo(f"Translating: {intent!r}")
    typer.echo(f"Provider:    {provider}")

    try:
        authoring = create_formula_authoring_use_cases(
            provider=provider, model=model, formulas_path=formulas_path
        )
        translation = authoring.translate.execute(
            CreateIndicatorFromIntentRequest(intent=intent, indicator_name=name)
        )

        if translation.unsupported:
            typer.echo("\n[error] This intent cannot be expressed as a formula.", err=True)
            typer.echo(
                "        Tip:   Describe a mathematical combination of indicators.", err=True
            )
            raise typer.Exit(1)

        if not translation.success:
            typer.echo(f"\n[error] {translation.error_message}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\nFormula: {translation.formula}")

        result = authoring.persist.execute(
            PersistGeneratedFormulaRequest(
                formula=translation.formula,
                ast=translation.ast,
                intent=intent,
                requested_name=name,
                save=save,
            )
        )

        if result.auto_generated:
            typer.echo(f"Auto-generated name: {result.name}")

        if result.register_attempted:
            if result.registered:
                typer.echo(f"Registered: {result.name}")
            else:
                typer.echo(
                    f"Warning: Could not register formula in memory: {result.register_error}",
                    err=True,
                )

        if result.save_attempted:
            if result.saved:
                typer.echo(f"Saved to:   {resolve_formulas_path(formulas_path)}")
            else:
                typer.echo(f"Warning: Could not save formula: {result.save_error}", err=True)

        typer.echo(f"\nUse it: saham indicator compute {result.name} TICKER")

    except typer.Exit:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "api key" in msg or "authentication" in msg:
            typer.echo(f"[error] {e}", err=True)
            typer.echo(
                f"        Tip:   Set the API key environment variable for {provider}.", err=True
            )
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
    response = create_list_formulas_use_case(formulas_path).execute()
    print_formula_list(
        response.registry,
        response.stored_formulas,
        show_formulas,
        response.formulas_path,
    )


def show(
    name: Annotated[str, typer.Argument(help="Formula name")],
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    response = create_show_formula_use_case(formulas_path).execute(name)

    if not response.found:
        typer.echo(f"[error] Formula '{response.requested_name}' not found.", err=True)
        typer.echo("\nAvailable formulas:", err=True)
        for formula_name in response.available_names:
            typer.echo(f"  {formula_name}", err=True)
        raise typer.Exit(1)

    stored = response.formula
    typer.echo(f"\nName:    {stored.name}")
    typer.echo(f"Formula: {stored.formula}")
    if stored.intent:
        typer.echo(f"Intent:  {stored.intent}")
    typer.echo(f"Created: {stored.created.strftime('%Y-%m-%d %H:%M:%S')}")


def delete(
    name: Annotated[str, typer.Argument(help="Formula name to delete")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    use_case = create_delete_formula_use_case(formulas_path)
    preview = use_case.preview(name)

    if preview.eligibility is DeleteEligibility.BUILTIN_PROTECTED:
        typer.echo(f"[error] Cannot delete built-in indicator: {preview.name}", err=True)
        raise typer.Exit(1)

    if preview.eligibility is DeleteEligibility.NOT_FOUND:
        typer.echo(f"[error] Formula '{preview.name}' not found in storage.", err=True)
        raise typer.Exit(1)

    if not force:
        stored = preview.formula
        typer.echo("\nFormula to delete:")
        typer.echo(f"  Name:    {stored.name}")
        typer.echo(f"  Formula: {stored.formula}")
        if not typer.confirm("\nDelete this formula?"):
            typer.echo("Cancelled.")
            raise typer.Exit(0)

    try:
        deleted = use_case.commit(preview.name)
        if deleted:
            typer.echo(f"Deleted {preview.name}.")
        else:
            typer.echo(f"[error] Formula '{preview.name}' not found.", err=True)
            raise typer.Exit(1)
    except FormulaStoreError as e:
        typer.echo(f"[error] Failed to delete formula: {e}", err=True)
        raise typer.Exit(1)
