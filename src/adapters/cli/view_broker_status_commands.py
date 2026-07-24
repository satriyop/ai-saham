"""
Broker provider/session status command.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_contract_cli import echo_json, resolve_output_format
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewSubjectKind,
    build_view_envelope,
)
from src.infrastructure.config.app_config import load_app_config


def broker_status(
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Check broker data provider status.

    Shows status of all available providers.
    """
    output_format = resolve_output_format(fmt or "table")
    cfg = load_app_config()

    idx_status = {
        "provider": "idx",
        "available": True,
        "auth_required": False,
        "detail": "public API, no auth required",
    }

    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session

    _session = get_stockbit_session()
    stockbit_active = bool(_session and _session.authenticated)
    age_h: float | None = None
    if stockbit_active:
        profile_dir = Path(cfg.storage.stockbit_profile_dir)
        marker = profile_dir / ".logged_in_at"
        if marker.exists():
            import time as _time

            try:
                age_h = round((_time.time() - float(marker.read_text())) / 3600, 1)
            except Exception:
                pass

    stockbit_status = {
        "provider": "stockbit",
        "available": stockbit_active,
        "auth_required": True,
        "session_age_hours": age_h,
        "detail": (
            f"Active ({age_h}h old)" if stockbit_active and age_h is not None
            else ("Active" if stockbit_active else "No session")
        ),
    }

    if output_format == "json":
        echo_json(
            build_view_envelope(
                subject_id="status",
                verb="status",
                status=ViewResultStatus.OK,
                data={
                    "default_provider": cfg.broker.provider,
                    "providers": [idx_status, stockbit_status],
                },
                source="runtime",
                scope="meta",
                subject_kind=ViewSubjectKind.DESK,
                fetch_hint="saham fetch stockbit login",
            )
        )
        return

    # IDX provider (always available)
    typer.echo(
        "IDX provider: "
        + typer.style("Available", fg=typer.colors.GREEN)
        + " (public API, no auth required)"
    )

    if stockbit_active:
        age_str = f" ({age_h}h old)" if age_h is not None else ""
        typer.echo(
            "Stockbit-Session provider: "
            + typer.style(f"Active{age_str}", fg=typer.colors.GREEN)
            + " — use --provider stockbit"
        )
    else:
        typer.echo(
            "Stockbit-Session provider: "
            + typer.style("No session", fg=typer.colors.YELLOW)
            + " (run 'saham fetch stockbit login' to set up)"
        )

    typer.echo(f"\nDefault provider: {cfg.broker.provider}")
