"""Single composition root for the optional daily cockpit TUI.

Phase 0: no infrastructure wiring yet — app is chrome-only.
Later phases inject use-case callables here (accumulation, pre-open, plan,
explicit fetch). All infrastructure imports must remain confined to this module.

Layer: Adapter composition root
"""

from __future__ import annotations

from src.adapters.tui.main import CockpitApp


def create_tui_app() -> CockpitApp:
    """Build the cockpit app. Name kept for CLI/packaging stability."""
    return CockpitApp()


# Alias preferred by ADR-051 naming; create_tui_app remains the public entry.
create_cockpit_app = create_tui_app
