"""
DTOs for the intraday confirmation command workflow.

Layer: Application
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
)
from src.domain.value_objects.intraday_confirmation import IntradayConfirmation


@dataclass(frozen=True)
class RunIntradayConfirmationWorkflowRequest:
    """Request DTO for running the full intraday confirmation workflow."""

    sidecar_path: Path
    output_path: Path
    max_stop_pct: Decimal
    manual_prices: dict[str, Decimal]
    track_file: Path | None
    live_auto_resolution_enabled: bool


@dataclass(frozen=True)
class RunIntradayConfirmationWorkflowResult:
    """Result DTO for the intraday confirmation command workflow."""

    observations: dict[str, OpeningPriceObservation]
    confirmations: tuple[IntradayConfirmation, ...]
    confirmed_date: date
    max_stop_pct: Decimal
    extras: dict[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    output_path: Path | None = None
