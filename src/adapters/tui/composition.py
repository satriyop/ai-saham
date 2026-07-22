"""Single composition root for the optional TUI adapter.

Phase 1 deliberately constructs only the shell. No infrastructure, provider,
repository, config loader, or application capability is composed here.

Layer: Adapter composition root
"""

from src.adapters.tui.main import SahamTuiApp


def create_tui_app() -> SahamTuiApp:
    return SahamTuiApp()
