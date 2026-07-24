"""
CLI: view broker list — tracked desk codes + Foreign/Local classification.

Layer: Adapter
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_contract_cli import (
    desk_envelope,
    echo_json,
    resolve_output_format,
)
from src.application.services.broker_desk_from_daily_flow import classify_desk_type
from src.domain.entities.broker_flow import BrokerType
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.config.stockbit_config import load_stockbit_config


def broker_list(
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """List configured tracked broker codes and Foreign/Local type."""
    output_format = resolve_output_format(fmt or "table")
    sb = load_stockbit_config()
    ia = load_institutional_accumulation_config()
    codes = sb.tracked_broker_codes
    desks = []
    for code in codes:
        btype = classify_desk_type(code, ia.foreign_broker_codes)
        if btype == BrokerType.FOREIGN:
            label = "Foreign"
        elif btype == BrokerType.LOCAL:
            label = "Local"
        else:
            label = "unknown"
        desks.append({"code": code, "type": label, "broker_type": btype.value})

    if output_format == "json":
        echo_json(
            desk_envelope(
                code="*",
                verb="list",
                source="config",
                scope="tracked_brokers",
                scope_note="Configured tracked desks (stockbit.broker_codes.tracked)",
                data={"desks": desks},
            )
        )
        return

    typer.echo("Tracked broker desks (broker_daily_flow):")
    typer.echo("-" * 40)
    for row in desks:
        typer.echo(f"  {row['code']:4}  {row['type']}")
    typer.echo("-" * 40)
    typer.echo("Deep-dives: saham view broker show|top-stocks|flow|history <CODE>")
