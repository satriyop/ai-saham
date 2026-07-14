"""
CLI command for importing broker flow data from CSV.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_broker_display import display_import_preview
from src.adapters.cli.fetch_broker_workflow_factory import (
    create_import_broker_data_use_case,
    load_broker_import_mapping,
)
from src.application.use_case.import_broker_data_use_case import (
    ImportBrokerDataRequest,
)
from src.domain.ports.csv_broker_parser import CsvBrokerParserError, ErrorStrategy
from src.infrastructure.config.app_config import load_app_config


def broker_import(
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Path to CSV file to import",
            exists=True,
            readable=True,
        ),
    ],
    preview: Annotated[
        bool,
        typer.Option(
            "--preview",
            "-p",
            help="Preview import without saving",
        ),
    ] = False,
    mapping: Annotated[
        Optional[str],
        typer.Option(
            "--mapping",
            "-m",
            help="Custom mapping name or YAML file path",
        ),
    ] = None,
    on_error: Annotated[
        str,
        typer.Option(
            "--on-error",
            help="Error handling: skip (default), fail, report",
        ),
    ] = "skip",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """
    Import broker flow data from a CSV file.

    Supports auto-detection of CSV format based on column headers:

    \b
    Simple format (aggregate foreign flow):
      date,ticker,foreign_buy_value,foreign_sell_value,foreign_buy_lot,
      foreign_sell_lot,total_value,total_lot

    \b
    Detailed format (broker transactions):
      date,ticker,broker_code,broker_name,broker_type,buy_lot,sell_lot,
      buy_value,sell_value

    Examples:
        saham fetch broker-import data.csv                  # Auto-detect format
        saham fetch broker-import data.csv --preview        # Preview without saving
        saham fetch broker-import data.csv --mapping rti    # Use custom mapping
        saham fetch broker-import data.csv --on-error fail  # Stop on first error
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    try:
        error_strategy = ErrorStrategy.parse(on_error)
    except ValueError:
        typer.echo(
            typer.style(f"Invalid --on-error value: {on_error}", fg=typer.colors.RED)
        )
        typer.echo("Valid values: skip, fail, report")
        raise typer.Exit(1)

    # Load custom mapping if specified
    mapping_config = None
    if mapping:
        try:
            mapping_config = load_broker_import_mapping(mapping)
            if mapping_config:
                typer.echo(f"Using mapping: {mapping_config.name}")
        except CsvBrokerParserError as e:
            typer.echo(typer.style(f"Mapping error: {e}", fg=typer.colors.RED))
            raise typer.Exit(1)

    # Initialize dependencies using factory
    use_case = create_import_broker_data_use_case(resolved_db)

    # Create request
    request = ImportBrokerDataRequest(
        file_path=file_path,
        preview_only=preview,
        error_strategy=error_strategy,
        mapping=mapping_config,
    )

    try:
        # Execute import
        if preview:
            typer.echo(f"Previewing {file_path.name}...")
        else:
            typer.echo(f"Importing {file_path.name}...")

        response = use_case.execute(request)

        # Display format detected
        typer.echo(f"Format detected: {response.format_detected.value}")

        # Preview mode output
        if preview:
            display_import_preview(response)

        # Import mode output
        else:
            if response.success:
                typer.echo(
                    typer.style(
                        f"\nImported {response.imported_count} broker summaries",
                        fg=typer.colors.GREEN,
                    )
                )

                # Show summary stats
                if response.summaries:
                    tickers = sorted(set(s.ticker for s in response.summaries))
                    dates = sorted(s.date for s in response.summaries)

                    typer.echo(f"Tickers: {', '.join(tickers)}")
                    if len(dates) > 1:
                        typer.echo(f"Date range: {dates[0]} to {dates[-1]}")
                    else:
                        typer.echo(f"Date: {dates[0]}")

                if response.skipped_count > 0:
                    typer.echo(
                        typer.style(
                            f"Skipped {response.skipped_count} invalid rows",
                            fg=typer.colors.YELLOW,
                        )
                    )
            else:
                typer.echo(
                    typer.style(f"\nImport failed: {response.message}", fg=typer.colors.RED)
                )
                raise typer.Exit(1)

            # Show errors if using report strategy
            if response.errors and error_strategy == ErrorStrategy.REPORT:
                typer.echo(f"\n{typer.style('Parse Errors:', fg=typer.colors.YELLOW)}")
                for error in response.errors[:10]:
                    typer.echo(f"  - {error}")
                if len(response.errors) > 10:
                    typer.echo(f"  ... and {len(response.errors) - 10} more")

    except CsvBrokerParserError as e:
        typer.echo(typer.style(f"Parse error: {e}", fg=typer.colors.RED))
        raise typer.Exit(1)
