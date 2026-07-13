"""
CLI commands for swing tuning patch validation and application.

Layer: Adapter
"""

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from src.adapters.cli.trade_swing_tuning_patch_display import (
    display_swing_tuning_patch_apply,
    display_swing_tuning_patch_dry_run,
    display_swing_tuning_patch_validation,
    display_swing_tuning_patch_verify,
)
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchApplier,
    SwingTuningPatchDryRunPlanner,
    SwingTuningPatchValidator,
    SwingTuningPatchVerifier,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.infrastructure.config.swing_tuning_document_writer import (
    read_swing_tuning_document,
    write_swing_tuning_document,
)


def _git_path_is_dirty(path: Path, config_root: Path) -> bool:
    root = Path(config_root).resolve()
    try:
        relative_path = path.resolve().relative_to(root)
    except ValueError:
        return True
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", str(relative_path)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return True
    return bool(result.stdout.strip())


def validate_tuning_patch(
    patch_path: Annotated[
        Path,
        typer.Argument(help="Path to exported swing tuning patch JSON"),
    ],
    config_root: Annotated[
        Path,
        typer.Option("--config-root", help="Repository/config root for YAML resolution"),
    ] = Path("."),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
) -> None:
    """Validate exported swing tuning patch JSON without applying it."""
    report = SwingTuningPatchValidator(
        document_loader=swing_tuning_document_loader(config_root)
    ).validate(patch_path)

    if output_format == "json":
        payload = {
            **report.to_dict(),
            "schema_version": 1,
            "artifact_type": "swing_tuning_patch_validation",
        }
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_tuning_patch_validation(report)


def apply_tuning_patch(
    patch_path: Annotated[
        Path,
        typer.Argument(help="Path to exported swing tuning patch JSON"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show changes without writing YAML."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Required for real apply. Writes YAML when checks pass."),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Verify target YAML values match proposed values."),
    ] = False,
    config_root: Annotated[
        Path,
        typer.Option("--config-root", help="Repository/config root for YAML resolution"),
    ] = Path("."),
    log_path: Annotated[
        Path,
        typer.Option("--log", help="Apply audit log JSONL path"),
    ] = Path("journals/swing_tuning_apply_log.jsonl"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
) -> None:
    """Dry-run or explicitly apply exported swing tuning patch changes."""
    selected_modes = sum(1 for selected in (dry_run, yes, verify) if selected)
    if selected_modes > 1:
        typer.echo("Error: choose only one of --dry-run, --yes, or --verify.", err=True)
        raise typer.Exit(1)
    if selected_modes == 0:
        typer.echo(
            "Error: use --dry-run to preview, --yes to apply, or --verify to check.",
            err=True,
        )
        raise typer.Exit(1)

    if verify:
        report = SwingTuningPatchVerifier(
            document_loader=swing_tuning_document_loader(config_root)
        ).verify(patch_path)
        if output_format == "json":
            payload = {
                **report.to_dict(),
                "schema_version": 1,
                "artifact_type": "swing_tuning_patch_verify",
            }
            typer.echo(json.dumps(payload, indent=2, default=str))
            if not report.verified:
                raise typer.Exit(1)
            return

        display_swing_tuning_patch_verify(report)
        if not report.verified:
            raise typer.Exit(1)
        return

    if dry_run:
        report = SwingTuningPatchDryRunPlanner(
            document_loader=swing_tuning_document_loader(config_root)
        ).plan(patch_path)
        if output_format == "json":
            payload = {
                **report.to_dict(),
                "schema_version": 1,
                "artifact_type": "swing_tuning_patch_dry_run",
                "apply": {
                    "performed": False,
                    "reason": "dry-run only",
                },
            }
            typer.echo(json.dumps(payload, indent=2, default=str))
            return

        display_swing_tuning_patch_dry_run(report)
        return

    report = SwingTuningPatchApplier(
        config_root=config_root,
        document_loader=swing_tuning_document_loader(config_root),
        document_reader=read_swing_tuning_document,
        document_writer=write_swing_tuning_document,
        target_dirty_checker=lambda path: _git_path_is_dirty(path, config_root),
    ).apply(
        patch_path,
        confirmed=yes,
        log_path=log_path,
    )
    if output_format == "json":
        payload = {
            **report.to_dict(),
            "schema_version": 1,
            "artifact_type": "swing_tuning_patch_apply",
        }
        typer.echo(json.dumps(payload, indent=2, default=str))
        if not report.applied:
            raise typer.Exit(1)
        return

    display_swing_tuning_patch_apply(report)
    if not report.applied:
        raise typer.Exit(1)
