"""
CLI commands for swing tuning status and saved review history.

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_swing_tuning_loop_status_display import (
    display_swing_tuning_loop_status,
)
from src.adapters.cli.trade_swing_tuning_measurement_display import (
    display_swing_tuning_post_apply_measurement,
)
from src.adapters.cli.trade_swing_tuning_review_display import (
    display_swing_tuning_review_comparison,
    display_swing_tuning_review_report,
)
from src.application.services.swing_tuning_loop_status import (
    SwingTuningLoopStatusService,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)


def tuning_status(
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Swing tuning review journal path"),
    ] = None,
    patch_path: Annotated[
        Path,
        typer.Option("--patch", help="Exported swing tuning patch JSON path"),
    ] = Path("journals/swing_tuning_patch.json"),
    apply_log: Annotated[
        Path,
        typer.Option("--apply-log", help="Swing tuning apply log JSONL path"),
    ] = Path("journals/swing_tuning_apply_log.jsonl"),
    config_root: Annotated[
        Path,
        typer.Option("--config-root", help="Repository/config root for YAML resolution"),
    ] = Path("."),
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """Show read-only status for the swing tuning loop."""
    cfg = load_app_config()
    output_format = output_format or cfg.analysis.format
    journal_path = journal or Path(cfg.storage.swing_tuning_review_journal)
    report = SwingTuningLoopStatusService(
        SwingTuningReviewJsonlWriter(journal_path),
        document_loader=swing_tuning_document_loader(config_root),
    ).status(
        review_journal_path=journal_path,
        patch_path=patch_path,
        apply_log_path=apply_log,
        apply_records=SwingTuningReviewJsonlWriter(apply_log).read_all(),
    )

    if output_format == "json":
        payload = {
            "schema_version": 1,
            "artifact_type": "swing_tuning_loop_status",
            **report.to_dict(),
        }
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_tuning_loop_status(report)


def review_tuning_swing(
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Swing tuning review journal path"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Number of recent saved runs to show", min=1),
    ] = 10,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    compare_latest: Annotated[
        bool,
        typer.Option(
            "--compare-latest",
            help="Compare latest saved review against the previous saved review",
        ),
    ] = False,
    measure_latest_apply: Annotated[
        bool,
        typer.Option(
            "--measure-latest-apply",
            help="Compare saved reviews before and after the latest applied patch",
        ),
    ] = False,
    apply_log: Annotated[
        Path,
        typer.Option("--apply-log", help="Swing tuning apply log JSONL path"),
    ] = Path("journals/swing_tuning_apply_log.jsonl"),
) -> None:
    """Review saved swing tuning review runs."""
    cfg = load_app_config()
    output_format = output_format or cfg.analysis.format
    journal_path = journal or Path(cfg.storage.swing_tuning_review_journal)
    journal_service = SwingTuningReviewJournal(
        SwingTuningReviewJsonlWriter(journal_path)
    )
    report = journal_service.review(limit=limit)
    comparison = journal_service.compare_latest() if compare_latest else None
    measurement = (
        journal_service.measure_latest_apply(
            SwingTuningReviewJsonlWriter(apply_log).read_all()
        )
        if measure_latest_apply
        else None
    )

    if output_format == "json":
        payload = {
            "schema_version": 1,
            "artifact_type": "swing_tuning_review_history",
            "journal": str(journal_path),
            **report.to_dict(),
        }
        if comparison is not None:
            payload["comparison"] = comparison.to_dict()
        if measurement is not None:
            payload["post_apply_measurement"] = measurement.to_dict()
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_tuning_review_report(report, journal_path)
    if comparison is not None:
        display_swing_tuning_review_comparison(comparison)
    if measurement is not None:
        display_swing_tuning_post_apply_measurement(measurement)
