"""
CLI: view broker list — tracked desk codes + Foreign/Local classification.

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.application.services.broker_desk_from_daily_flow import classify_desk_type
from src.domain.entities.broker_flow import BrokerType
from src.infrastructure.config.stockbit_config import load_stockbit_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)


def broker_list() -> None:
    """List configured tracked broker codes and Foreign/Local type."""
    sb = load_stockbit_config()
    ia = load_institutional_accumulation_config()
    codes = sb.tracked_broker_codes
    typer.echo("Tracked broker desks (broker_daily_flow):")
    typer.echo("-" * 40)
    for code in codes:
        btype = classify_desk_type(code, ia.foreign_broker_codes)
        if btype == BrokerType.FOREIGN:
            label = "Foreign"
        elif btype == BrokerType.LOCAL:
            label = "Local"
        else:
            label = "—"
        typer.echo(f"  {code:4}  {label}")
    typer.echo("-" * 40)
    typer.echo("Deep-dives: saham view broker show|top-stocks|flow|history <CODE>")
