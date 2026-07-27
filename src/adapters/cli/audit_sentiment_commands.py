"""CLI: saham audit sentiment — historical sentiment accuracy.

Not a live trade input. Not inspect (live lens).

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.inspect_sentiment_display import display_sentiment_audit
from src.adapters.cli.inspect_sentiment_workflow_factory import (
    create_audit_sentiment_use_case,
)
from src.application.use_case.audit_sentiment_use_case import AuditSentimentRequest
from src.infrastructure.config.app_config import load_app_config


def sentiment_audit(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Audit past sentiment accuracy against actual price moves.

    Finds logged sentiment predictions and checks their outcomes
    after 1, 3, and 5 trading days.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    typer.echo("Auditing past sentiment predictions...")

    try:
        use_case = create_audit_sentiment_use_case(db_path=resolved_db)
        response = use_case.execute(AuditSentimentRequest())
        display_sentiment_audit(response)

    except Exception as e:
        typer.echo(f"Failed to audit sentiment: {e}", err=True)
        raise typer.Exit(1)
