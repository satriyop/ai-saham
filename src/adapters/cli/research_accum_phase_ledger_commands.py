"""CLI: backfill setup phase ledger from learning observations.

Layer: Adapter
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.backfill_setup_phase_ledger import (
    backfill_setup_phase_ledger_from_observations,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
    SQLiteSetupPhaseLedgerRepository,
)


def backfill_phase_ledger(
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Backfill setup_phase_ledger from ACCUMULATION_DISCOVERY observations.

    Safe to re-run (last-wins upsert per ticker/as_of/family/workflow).
    Run once after upgrade so sequence validation has closed-session history
    without mining the full observation table on every screen.
    """
    cfg = load_app_config()
    resolved = db_path or Path(cfg.storage.db_path)
    observations = SQLiteLearningArtifactRepository(resolved)
    ledger = SQLiteSetupPhaseLedgerRepository(resolved)
    report = backfill_setup_phase_ledger_from_observations(
        observation_repository=observations,
        ledger_repository=ledger,
    )
    if fmt == "json":
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return
    typer.echo("Setup phase ledger backfill")
    typer.echo(f"  observations_seen: {report.observations_seen}")
    typer.echo(f"  rows_written:      {report.rows_written}")
    typer.echo(f"  rows_updated:      {report.rows_updated}")
    typer.echo(f"  rows_identical:    {report.rows_identical}")
    typer.echo(f"  rows_skipped:      {report.rows_skipped}")
