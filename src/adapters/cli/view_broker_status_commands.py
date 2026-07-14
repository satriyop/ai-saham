"""
Broker provider/session status command.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path

import typer

from src.infrastructure.config.app_config import load_app_config


def broker_status() -> None:
    """
    Check broker data provider status.

    Shows status of all available providers.
    """
    cfg = load_app_config()
    # IDX provider (always available)
    typer.echo("IDX provider: " + typer.style("Available", fg=typer.colors.GREEN)
               + " (public API, no auth required)")

    # Stockbit Playwright session provider
    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session
    _session = get_stockbit_session()
    if _session and _session.authenticated:
        profile_dir = Path(cfg.storage.stockbit_profile_dir)
        marker = profile_dir / ".logged_in_at"
        age_h: float | None = None
        if marker.exists():
            import time as _time
            try:
                age_h = round((_time.time() - float(marker.read_text())) / 3600, 1)
            except Exception:
                pass
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
