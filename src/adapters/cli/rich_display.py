"""
Shared Rich display helpers for CLI adapters.

Layer: Adapter
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def console() -> Console:
    """Return a deterministic console for test-friendly CLI rendering."""
    return Console(color_system=None, highlight=False, width=100)


def panel(renderable, title: str, subtitle: str | None = None) -> Panel:
    return Panel(renderable, title=title, subtitle=subtitle, border_style="cyan")


def compact_table(*, show_header: bool = True) -> Table:
    return Table(
        show_header=show_header,
        header_style="bold cyan",
        box=None,
        pad_edge=False,
        collapse_padding=True,
    )
