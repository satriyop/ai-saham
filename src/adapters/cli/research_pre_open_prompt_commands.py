"""
Prompt command for the opening session learning loop.

Generates a copy-pasteable AI prompt from session data.

Layer: Adapter
"""

from typing import Annotated, Optional

import typer

from src.adapters.cli.research_pre_open_paths import (
    opening_day_dir,
    parse_session_date,
)


def prompt(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    print_output: Annotated[bool, typer.Option("--print", help="Print prompt to stdout")] = False,
) -> None:
    """
    Generate a copy-pasteable AI prompt from today's session data.

    Includes screener predictions, actual price outcomes, and accuracy metrics
    in a format ready to paste into Claude, ChatGPT, or any AI assistant.

    Saves: data/opening/YYYYMMDD/prompt.md

    Examples:
        saham research pre-open prompt
        saham research pre-open prompt --print | pbcopy   # copy to clipboard (macOS)
    """
    run_date = parse_session_date(date_str)

    try:
        from src.application.use_case.opening_prompt_use_case import build_prompt
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    try:
        content = build_prompt(run_date)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    out_dir = opening_day_dir(run_date)
    typer.echo(f"Prompt saved → {out_dir}/prompt.md")

    if print_output:
        typer.echo(content)
