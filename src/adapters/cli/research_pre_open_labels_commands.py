"""
CLI: saham research pre-open labels

Generate open_30m outcome labels from saved pre-open observations + learn track data.
Session-horizon twin of research signal labels (multi-day); separate command
so agents never mix open_30m into SignalLabelHorizon pipelines.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.learn_command_paths import parse_learn_date
from src.infrastructure.config.app_config import load_app_config


def pre_open_labels(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    no_persist: Annotated[
        bool,
        typer.Option(
            "--no-persist",
            help="Compute only; do not write open_30m_labels.json",
        ),
    ] = False,
) -> None:
    """
    Generate open_30m outcome labels for a pre-open session date.

    Requires saved screen_pre_open observations (research pre-open capture)
    and learn track files. Writes data/opening/YYYYMMDD/open_30m_labels.json.

    Examples:
        saham research pre-open labels
        saham research pre-open labels --date 2026-06-18
    """
    run_date = parse_learn_date(date_str)
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    try:
        from src.application.use_case.generate_pre_open_open30m_labels_use_case import (
            generate_pre_open_open30m_labels,
        )
        from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
            SQLiteCandidateObservationsRepository,
        )
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    observations_repo = None
    if resolved_db.exists():
        try:
            observations_repo = SQLiteCandidateObservationsRepository(resolved_db)
        except Exception as e:
            typer.echo(
                f"Warning: observations DB unavailable ({e}); snapshot fallback.",
                err=True,
            )

    try:
        result = generate_pre_open_open30m_labels(
            run_date,
            observations_repository=observations_repo,
            persist=not no_persist,
        )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"open_30m labels: source={result.decision_source}  "
        f"n={result.observation_count}  labeled={result.labeled_count}  "
        f"unavailable={result.unavailable_count}"
    )
    if result.output_path:
        typer.echo(f"Saved → {result.output_path}")

    hist: dict[str, int] = {}
    for lb in result.labels:
        hist[lb.outcome] = hist.get(lb.outcome, 0) + 1
    if hist:
        typer.echo(
            "  Outcomes: " + "  ".join(f"{k}={v}" for k, v in sorted(hist.items()))
        )
