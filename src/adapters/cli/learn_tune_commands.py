"""
Tune command for the opening session learning loop.

Calls DeepSeek AI with accuracy grade and saves config recommendations.

Layer: Adapter
"""

import os
from typing import Annotated, Optional

import typer

from src.adapters.cli.learn_command_paths import (
    opening_day_dir,
    parse_learn_date,
)


def tune(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="DeepSeek API key (overrides env)")
    ] = None,
    allow_invalid_snapshot: Annotated[
        bool,
        typer.Option(
            "--allow-invalid-snapshot",
            help="Allow AI tuning from low-confidence or out-of-window snapshot data",
        ),
    ] = False,
) -> None:
    """
    Call DeepSeek AI with today's accuracy grade and save config recommendations.

    Requires: grade.json from today (run `saham learn grade` first).
    Reads DEEPSEEK_API_KEY from environment if --api-key not provided.

    Saves: data/opening/YYYYMMDD/tune.json + tune.md

    Examples:
        saham learn tune
        saham learn tune --date 2026-06-17
    """
    run_date = parse_learn_date(date_str)
    resolved_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    if not resolved_key:
        typer.echo("No DeepSeek API key. Set DEEPSEEK_API_KEY or pass --api-key.", err=True)
        raise typer.Exit(1)

    try:
        from src.application.use_case.opening_tune_use_case import (
            OpeningTuneRequest,
            OpeningTuneUseCase,
        )
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    use_case = OpeningTuneUseCase()
    typer.echo("Calling DeepSeek for config recommendations...")

    result = use_case.execute(
        OpeningTuneRequest(
            run_date=run_date,
            deepseek_api_key=resolved_key,
            allow_invalid_snapshot=allow_invalid_snapshot,
        )
    )

    if result.get("skipped"):
        typer.echo(f"Skipped: {result.get('reason')}", err=True)
        raise typer.Exit(1)

    out_dir = opening_day_dir(run_date)
    typer.echo(f"Saved → {out_dir}/tune.json + tune.md  ({result.get('tokens_used', 0)} tokens)")
    if result.get("summary"):
        typer.echo(f"\nSummary: {result['summary']}")
    if result.get("top_finding"):
        typer.echo(f"Top finding: {result['top_finding']}")

    recs = result.get("config_recommendations", {})
    if recs:
        typer.echo("\nRecommended changes:")
        for file_key, params in recs.items():
            typer.echo(f"  [{file_key}]")
            for param, change in params.items():
                typer.echo(
                    f"    {param}: {change.get('current')} → {change.get('suggested')}"
                    f"  # {change.get('reason', '')}"
                )
