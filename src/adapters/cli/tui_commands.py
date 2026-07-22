"""Lazy CLI launcher for the optional Textual research workspace.

This module deliberately has no top-level import from ``textual`` or
``src.adapters.tui`` so every base CLI command remains available without the
optional TUI dependency.

Layer: Adapter
"""

from collections.abc import Callable

import typer

MISSING_TUI_EXTRA_MESSAGE = (
    "TUI support is not installed. Install this checkout with: "
    "pip install -e '.[tui]'"
)


def _load_tui_runner() -> Callable[[], None]:
    from src.adapters.tui.main import run_tui

    return run_tui


def tui() -> None:
    """Open the optional local terminal research workspace."""
    try:
        runner = _load_tui_runner()
    except ModuleNotFoundError as exc:
        if exc.name != "textual":
            raise
        typer.echo(MISSING_TUI_EXTRA_MESSAGE, err=True)
        raise typer.Exit(code=1) from None

    runner()
