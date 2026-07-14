"""
Shared Playwright availability guard for Stockbit CLI commands.

Layer: Adapter
"""

from __future__ import annotations

import typer


def require_playwright_cli() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        typer.echo(
            "playwright not installed.\nRun: pip install playwright && playwright install chromium",
            err=True,
        )
        raise typer.Exit(1)
