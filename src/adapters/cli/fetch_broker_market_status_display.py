"""
Market status echo helper for broker fetch CLI commands.

Layer: Adapter
"""

from __future__ import annotations

import typer


def echo_stockbit_market_status(*, leading_blank: bool = False) -> None:
    from src.infrastructure.browser.stockbit_market_time import (
        format_market_status_line,
        get_display_market_status,
    )

    if leading_blank:
        typer.echo("")
    typer.echo(format_market_status_line(get_display_market_status()))
